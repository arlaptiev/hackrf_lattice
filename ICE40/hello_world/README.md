# iCE40 Hello World UART -> RGB LED

This sample project for iCE40UP5K receives one UART byte from your computer and updates the onboard RGB LED state.

Behavior:
- Send `0x00` -> RGB LED off
- Send `0x01` -> red on
- Send `0x02` -> green on
- Send `0x04` -> blue on
- Send `0x07` -> white (all channels on)
- Send `0x55` -> brief white debug flash (UART receive indicator)
- Only command bytes `0x00..0x07` are accepted; other bytes are ignored to reduce flicker from line noise

## Project layout

- `src/top.v`: FPGA design (internal 48 MHz oscillator + UART RX + RGB LED control)
- `pins.pcf`: board pin mapping (must be verified for your board)
- `Makefile`: synth/place-route/bitstream/program flow
- `send_byte.py`: host script to send one byte over serial

## 1) Set your board pins

Edit `pins.pcf` to match your board wiring:

- `rgb0/rgb1/rgb2` must map to your on-board RGB LED pins
- `uart_rx` must map to the FPGA pin connected to your USB-UART TX line

## 2) Build bitstream

```bash
make
```

Quick sanity test (no UART): build the simple RGB blink bitstream.

```bash
make clean
make TOP=top_blink PCF=pins_blink.pcf
```

Blink + UART color control test:

```bash
make clean
make TOP=top_blink_uart PCF=pins.pcf
```

## 3) Program FPGA

Temporary (SRAM):

```bash
make sram
```

If you see `cdone: low` after `make sram`, use flash programming instead. Some boards/programmer paths do not support SRAM configuration reliably.

Persistent (SPI flash):

```bash
make prog
```

For the blink sanity test image, flash with:

```bash
iceprog build/top_blink.bin
```

For blink + UART color control image, flash with:

```bash
iceprog build/top_blink_uart.bin
```

## 4) Send test byte from computer

Install pyserial once:

```bash
python3 -m pip install pyserial
```

Send byte examples:

```bash
python3 send_byte.py /dev/cu.usbserial-100 0x01
python3 send_byte.py /dev/cu.usbserial-100 0x00
python3 send_byte.py /dev/cu.usbserial-100 A
```

## Notes

- UART settings are fixed at 115200, 8N1.
- The design uses the iCE40 internal oscillator (`SB_HFOSC`), so no external clock pin is required.
- `uart_rx` is configured with a pull-up in `pins.pcf` to keep the line stable when idle/disconnected.
- In `top_blink_uart`, byte `0x55` triggers a brief white flash as a UART receive indicator.
- Some iCE40 breakout boards do not include a user LED. If you only see a power LED (for example `VBUS_5V`), this project cannot show visual changes until you wire an external LED/GPIO or target another observable pin.
- The values in `pins.pcf` are board-dependent; verify `rgb0/rgb1/rgb2` and `uart_rx` against your exact board documentation.

## Troubleshooting

If build fails at `nextpnr-ice40` on macOS with a missing Python framework path (for example `python@3.14`), your Homebrew `nextpnr-ice40` is linked against a Python version that is not currently installed.

Try:

```bash
brew update
brew reinstall python nextpnr-ice40
```

Then rebuild:

```bash
make clean
make
```
