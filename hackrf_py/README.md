# Sunday Challenge SoapySDR Transmitter

This workspace contains a Python/SoapySDR implementation of `sunday_challenge.grc`.

The parsed GRC signal path is:

```text
music.wav -> audio gain -> WFM modulator -> rational resampler 25/3 -> IQ gain -> HackRF TX
```

The requested conda environment has been created as `hackrf_py`.

```powershell
conda activate hackrf_py
python sunday_challenge_soapy.py --dry-run
python sunday_challenge_soapy.py --list-devices
python sunday_challenge_soapy.py --probe-device
python sunday_challenge_soapy.py --tx --duration 10
```

By default the script only parses and prints the flowgraph. Add `--tx` to actually transmit.

Useful overrides:

```powershell
python sunday_challenge_soapy.py --wav C:\Users\vlady\Desktop\music.wav --tx --duration 10
python sunday_challenge_soapy.py --center-freq 102300000 --tx
```

The GRC serial has been updated to the HackRF serial SoapySDR reports on this
machine: `0000000000000000930c64dc2b2e93c3`.
