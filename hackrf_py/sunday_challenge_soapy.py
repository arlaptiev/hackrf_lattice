#!/usr/bin/env python
"""Run the sunday_challenge.grc WFM HackRF flowgraph with SoapySDR.

The original GRC graph is:

    WAV -> multiply_const(float) -> WFM TX -> rational_resampler(25/3)
        -> multiply_const(complex) -> Soapy HackRF sink

This script parses the GRC YAML directly, resolves the enabled block
parameters, and reproduces that DSP chain in Python/Numpy/Scipy.
"""

from __future__ import annotations

import argparse
import ast
import math
import sys
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import soundfile as sf
import yaml
from scipy import signal


@dataclass(frozen=True)
class FlowConfig:
    grc_path: Path
    wav_path: Path
    repeat: bool
    audio_rate: int
    quad_rate: int
    sample_rate: int
    center_freq: float
    driver: str
    serial: str | None
    bandwidth: float | None
    audio_gain: float
    iq_gain: complex
    max_dev: float
    tau: float
    resamp_interp: int
    resamp_decim: int
    amp: bool
    vga: float | None


class EvalError(ValueError):
    pass


def _eval_ast(node: ast.AST, names: dict[str, Any]) -> Any:
    if isinstance(node, ast.Expression):
        return _eval_ast(node.body, names)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in names:
            return names[node.id]
        if node.id == "True":
            return True
        if node.id == "False":
            return False
        raise EvalError(f"unknown name {node.id!r}")
    if isinstance(node, ast.UnaryOp):
        value = _eval_ast(node.operand, names)
        if isinstance(node.op, ast.UAdd):
            return +value
        if isinstance(node.op, ast.USub):
            return -value
        if isinstance(node.op, ast.Not):
            return not value
    if isinstance(node, ast.BinOp):
        left = _eval_ast(node.left, names)
        right = _eval_ast(node.right, names)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.FloorDiv):
            return left // right
        if isinstance(node.op, ast.Mod):
            return left % right
        if isinstance(node.op, ast.Pow):
            return left**right
    if isinstance(node, ast.List):
        return [_eval_ast(elt, names) for elt in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_eval_ast(elt, names) for elt in node.elts)
    raise EvalError(f"unsupported expression {ast.dump(node, include_attributes=False)}")


def resolve_expr(value: Any, names: dict[str, Any]) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if text == "":
        return ""
    try:
        return _eval_ast(ast.parse(text, mode="eval"), names)
    except (SyntaxError, EvalError, TypeError):
        return value


def block_is_enabled(block: dict[str, Any]) -> bool:
    return block.get("states", {}).get("state", "enabled") == "enabled"


def load_grc(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not parse as a GRC YAML mapping")
    return data


def resolve_variables(blocks: Iterable[dict[str, Any]]) -> dict[str, Any]:
    raw: dict[str, Any] = {}
    for block in blocks:
        if block.get("id") == "variable" and block_is_enabled(block):
            raw[block["name"]] = block.get("parameters", {}).get("value")

    resolved: dict[str, Any] = {}
    pending = dict(raw)
    while pending:
        progress = False
        for name, expr in list(pending.items()):
            value = resolve_expr(expr, resolved)
            unresolved_same_name = isinstance(value, str) and value.strip() in pending
            if not unresolved_same_name:
                resolved[name] = value
                del pending[name]
                progress = True
        if not progress:
            unresolved = ", ".join(sorted(pending))
            raise ValueError(f"could not resolve GRC variables: {unresolved}")
    return resolved


def find_block(blocks: list[dict[str, Any]], block_id: str) -> dict[str, Any]:
    matches = [b for b in blocks if b.get("id") == block_id and block_is_enabled(b)]
    if not matches:
        raise ValueError(f"enabled block {block_id!r} not found")
    if len(matches) > 1:
        raise ValueError(f"expected one enabled {block_id!r} block, found {len(matches)}")
    return matches[0]


def p(block: dict[str, Any], key: str, names: dict[str, Any], default: Any = None) -> Any:
    return resolve_expr(block.get("parameters", {}).get(key, default), names)


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def parse_iq_gain(value: Any) -> complex:
    if isinstance(value, complex):
        return value
    if isinstance(value, (int, float)):
        return complex(value, 0.0)
    return complex(float(value), 0.0)


def parse_serial(dev_args: Any) -> str | None:
    if dev_args is None:
        return None
    text = str(dev_args).strip().strip('"').strip("'")
    if not text:
        return None
    if "=" not in text:
        return text
    for part in text.split(","):
        key, _, value = part.partition("=")
        if key.strip() == "serial":
            return value.strip()
    return None


def parse_flowgraph(path: Path) -> FlowConfig:
    data = load_grc(path)
    blocks = data.get("blocks", [])
    if not isinstance(blocks, list):
        raise ValueError("GRC file has no blocks list")

    variables = resolve_variables(blocks)
    wav = find_block(blocks, "blocks_wavfile_source")
    wfm = find_block(blocks, "analog_wfm_tx")
    resampler = find_block(blocks, "rational_resampler_xxx")
    sink = find_block(blocks, "soapy_hackrf_sink")

    gain_blocks = [
        b
        for b in blocks
        if b.get("id") == "blocks_multiply_const_vxx" and block_is_enabled(b)
    ]
    audio_gain = 1.0
    iq_gain = 1.0 + 0.0j
    for block in gain_blocks:
        gain_type = str(p(block, "type", variables, "")).lower()
        const = p(block, "const", variables, 1)
        if gain_type == "float":
            audio_gain = float(const)
        elif gain_type == "complex":
            iq_gain = parse_iq_gain(const)

    return FlowConfig(
        grc_path=path,
        wav_path=Path(str(p(wav, "file", variables))),
        repeat=parse_bool(p(wav, "repeat", variables, False)),
        audio_rate=int(p(wfm, "audio_rate", variables)),
        quad_rate=int(p(wfm, "quad_rate", variables)),
        sample_rate=int(p(sink, "samp_rate", variables)),
        center_freq=float(p(sink, "center_freq", variables)),
        driver=str(resolve_expr(variables.get("driver", "hackrf"), variables)),
        serial=parse_serial(p(sink, "dev_args", variables)),
        bandwidth=float(p(sink, "bandwidth", variables)) or None,
        audio_gain=audio_gain,
        iq_gain=iq_gain,
        max_dev=float(p(wfm, "max_dev", variables)),
        tau=float(p(wfm, "tau", variables)),
        resamp_interp=int(p(resampler, "interp", variables)),
        resamp_decim=int(p(resampler, "decim", variables)),
        amp=parse_bool(p(sink, "amp", variables, False)),
        vga=float(p(sink, "vga", variables)) if p(sink, "vga", variables, None) is not None else None,
    )


def resample_to_rate(x: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if source_rate == target_rate:
        return x
    ratio = Fraction(target_rate, source_rate).limit_denominator()
    return signal.resample_poly(x, ratio.numerator, ratio.denominator).astype(np.float32)


def preemphasis(x: np.ndarray, sample_rate: int, tau: float, previous: float) -> tuple[np.ndarray, float]:
    if tau <= 0:
        return x, previous
    alpha = math.exp(-1.0 / (sample_rate * tau))
    x_with_prev = np.concatenate(([previous], x.astype(np.float32, copy=False)))
    y = x_with_prev[1:] - alpha * x_with_prev[:-1]
    return y.astype(np.float32, copy=False), float(x[-1]) if len(x) else previous


def audio_blocks(config: FlowConfig, chunk_frames: int, disable_preemphasis: bool) -> Iterable[np.ndarray]:
    if not config.wav_path.exists():
        raise FileNotFoundError(f"WAV/audio source not found: {config.wav_path}")

    previous_audio = 0.0
    while True:
        with sf.SoundFile(str(config.wav_path), mode="r") as audio_file:
            source_rate = int(audio_file.samplerate)
            while True:
                audio = audio_file.read(chunk_frames, dtype="float32", always_2d=True)
                if len(audio) == 0:
                    break
                mono = audio.mean(axis=1).astype(np.float32, copy=False)
                mono = resample_to_rate(mono, source_rate, config.audio_rate)
                mono *= np.float32(config.audio_gain)
                mono = np.clip(mono, -1.0, 1.0)
                if not disable_preemphasis:
                    mono, previous_audio = preemphasis(mono, config.audio_rate, config.tau, previous_audio)
                quad_audio = resample_to_rate(mono, config.audio_rate, config.quad_rate)
                yield quad_audio
        if not config.repeat:
            break


def modulated_iq_blocks(
    config: FlowConfig,
    chunk_frames: int,
    disable_preemphasis: bool,
) -> Iterable[np.ndarray]:
    phase = 0.0
    sensitivity = 2.0 * math.pi * config.max_dev / config.quad_rate
    for quad_audio in audio_blocks(config, chunk_frames, disable_preemphasis):
        phase_steps = quad_audio.astype(np.float64) * sensitivity
        phase_trace = np.cumsum(phase_steps) + phase
        if len(phase_trace):
            phase = float(np.mod(phase_trace[-1], 2.0 * math.pi))
        iq = np.exp(1j * phase_trace).astype(np.complex64)
        iq = signal.resample_poly(iq, config.resamp_interp, config.resamp_decim).astype(np.complex64)
        if config.iq_gain != 1.0 + 0.0j:
            iq *= np.complex64(config.iq_gain)
        yield iq


def print_summary(config: FlowConfig) -> None:
    print("Parsed sunday_challenge.grc")
    print(f"  WAV source:    {config.wav_path}")
    print(f"  Repeat WAV:    {config.repeat}")
    print(f"  Audio rate:    {config.audio_rate:,} sps")
    print(f"  WFM quad rate: {config.quad_rate:,} sps")
    print(f"  Output rate:   {config.sample_rate:,} sps")
    print(f"  Center freq:   {config.center_freq / 1e6:.6f} MHz")
    print(f"  Max dev:       {config.max_dev:,.0f} Hz")
    print(f"  Resampler:     {config.resamp_interp}/{config.resamp_decim}")
    print(f"  Soapy driver:  {config.driver}")
    print(f"  Serial:        {config.serial or '(not specified)'}")
    print(f"  Bandwidth:     {config.bandwidth or '(not specified)'}")
    print(f"  AMP:           {config.amp}")
    print(f"  VGA gain:      {config.vga if config.vga is not None else '(not specified)'}")


def list_devices() -> None:
    import SoapySDR

    devices = SoapySDR.Device.enumerate()
    if not devices:
        print("No SoapySDR devices found.")
        return
    for index, device in enumerate(devices):
        print(f"[{index}] {dict(device)}")


def configure_device(config: FlowConfig, clamp_gain: bool):
    import SoapySDR
    from SoapySDR import SOAPY_SDR_TX

    def open_device():
        candidates: list[str] = [f"driver={config.driver}"]
        if config.serial:
            serial = config.serial.strip()
            candidates.insert(0, f"driver={config.driver},serial={serial}")
            short_serial = serial[-16:]
            if short_serial != serial:
                candidates.insert(1, f"driver={config.driver},serial={short_serial}")

        errors: list[str] = []
        for candidate in candidates:
            try:
                return SoapySDR.Device(candidate)
            except Exception as exc:
                errors.append(f"{candidate}: {exc}")

        devices = [dict(d) for d in SoapySDR.Device.enumerate({"driver": config.driver})]
        available = "\n".join(f"  - {device}" for device in devices) or "  (none)"
        raise RuntimeError(
            "Could not open HackRF with any SoapySDR argument set:\n"
            + "\n".join(f"  - {error}" for error in errors)
            + "\nAvailable SoapySDR HackRF devices:\n"
            + available
        )

    sdr = open_device()
    sdr.setSampleRate(SOAPY_SDR_TX, 0, config.sample_rate)
    sdr.setFrequency(SOAPY_SDR_TX, 0, config.center_freq)
    if config.bandwidth:
        sdr.setBandwidth(SOAPY_SDR_TX, 0, config.bandwidth)

    gains = list(sdr.listGains(SOAPY_SDR_TX, 0))
    if "AMP" in gains:
        try:
            sdr.setGain(SOAPY_SDR_TX, 0, "AMP", 1.0 if config.amp else 0.0)
        except Exception as exc:
            print(f"Warning: could not set AMP gain: {exc}", file=sys.stderr)

    if config.vga is not None:
        gain_name = "VGA" if "VGA" in gains else None
        value = config.vga
        if gain_name and clamp_gain:
            gain_range = sdr.getGainRange(SOAPY_SDR_TX, 0, gain_name)
            minimum = float(gain_range.minimum())
            maximum = float(gain_range.maximum())
            clamped = min(max(value, minimum), maximum)
            if clamped != value:
                print(
                    f"Warning: clamped VGA gain from {value} to {clamped} "
                    f"(device range {minimum}..{maximum})",
                    file=sys.stderr,
                )
            value = clamped
        try:
            if gain_name:
                sdr.setGain(SOAPY_SDR_TX, 0, gain_name, value)
            else:
                sdr.setGain(SOAPY_SDR_TX, 0, value)
        except Exception as exc:
            print(f"Warning: could not set TX gain {value}: {exc}", file=sys.stderr)

    return sdr


def transmit(config: FlowConfig, args: argparse.Namespace) -> None:
    import SoapySDR
    from SoapySDR import SOAPY_SDR_CF32, SOAPY_SDR_TX

    sdr = configure_device(config, clamp_gain=not args.no_clamp_gain)
    stream = sdr.setupStream(SOAPY_SDR_TX, SOAPY_SDR_CF32, [0])
    started = False
    sent = 0
    max_samples = None
    if args.duration is not None:
        max_samples = int(args.duration * config.sample_rate)

    try:
        sdr.activateStream(stream)
        started = True
        for iq in modulated_iq_blocks(config, args.chunk_frames, args.no_preemphasis):
            if max_samples is not None:
                remaining = max_samples - sent
                if remaining <= 0:
                    break
                iq = iq[:remaining]
            offset = 0
            while offset < len(iq):
                view = iq[offset:]
                result = sdr.writeStream(stream, [view], len(view), timeoutUs=args.timeout_us)
                if result.ret < 0:
                    raise RuntimeError(f"SoapySDR writeStream failed: {SoapySDR.errToStr(result.ret)}")
                offset += result.ret
                sent += result.ret
    finally:
        if started:
            sdr.deactivateStream(stream)
        sdr.closeStream(stream)
    print(f"Transmitted {sent:,} complex samples ({sent / config.sample_rate:.3f} s).")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grc", type=Path, default=Path("sunday_challenge.grc"))
    parser.add_argument("--wav", type=Path, help="Override the WAV/audio file from the GRC.")
    parser.add_argument("--center-freq", type=float, help="Override transmit center frequency in Hz.")
    parser.add_argument("--serial", help="Override HackRF serial.")
    parser.add_argument("--duration", type=float, help="Transmit duration in seconds.")
    parser.add_argument("--chunk-frames", type=int, default=4096, help="Input audio frames per DSP chunk.")
    parser.add_argument("--timeout-us", type=int, default=1_000_000, help="SoapySDR write timeout.")
    parser.add_argument("--dry-run", action="store_true", help="Parse and print only. This is the default.")
    parser.add_argument("--probe-device", action="store_true", help="Open/configure the HackRF, then exit without TX.")
    parser.add_argument("--tx", action="store_true", help="Actually transmit. Without this, only parse/print.")
    parser.add_argument("--list-devices", action="store_true", help="List SoapySDR devices and exit.")
    parser.add_argument("--no-preemphasis", action="store_true", help="Disable the parsed WFM preemphasis step.")
    parser.add_argument("--no-clamp-gain", action="store_true", help="Do not clamp parsed gain to device range.")
    args = parser.parse_args(argv)

    if args.list_devices:
        list_devices()
        return 0

    config = parse_flowgraph(args.grc)
    if args.wav:
        config = FlowConfig(**{**config.__dict__, "wav_path": args.wav})
    if args.center_freq:
        config = FlowConfig(**{**config.__dict__, "center_freq": args.center_freq})
    if args.serial:
        config = FlowConfig(**{**config.__dict__, "serial": args.serial})

    print_summary(config)
    if args.probe_device:
        sdr = configure_device(config, clamp_gain=not args.no_clamp_gain)
        del sdr
        print("\nHackRF opened and configured successfully. No samples transmitted.")
        return 0

    if not args.tx:
        if not config.wav_path.exists():
            print(f"  Note: WAV source is missing: {config.wav_path}")
        print("\nDry run only. Add --tx to transmit.")
        return 0

    transmit(config, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
