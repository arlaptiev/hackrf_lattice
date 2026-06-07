# iCE40UP5K Open-Source FPGA Toolchain Setup

This guide is for getting started with a Lattice **iCE40UP5K** board, such as the iCE40 UltraPlus Breakout Board / iCE40UP5K-B-EVN, using the open-source FPGA flow.

The basic flow is:

```text
Verilog/SystemVerilog
  -> Yosys synthesis
  -> nextpnr-ice40 place-and-route
  -> IceStorm icepack bitstream packing
  -> IceStorm iceprog programming
  -> FPGA board
```

For the iCE40UP5K-B-EVN-style board, the usual nextpnr target options are:

```bash
--up5k --package sg48
```

You will still need the correct board-specific `.pcf` pin constraint file from the board schematic, user guide, or a known-good example project.

---

## 1. What each tool does

### Yosys

**Yosys** is the synthesis tool. It reads your Verilog and turns it into a gate-level netlist mapped toward iCE40 FPGA resources.

Example command:

```bash
yosys -p "synth_ice40 -top top -json build/top.json" src/top.v
```

What it produces:

```text
build/top.json
```

That JSON file describes the logic your design needs: LUTs, flip-flops, RAMs, carry chains, IOs, and their connections.

---

### nextpnr-ice40

**nextpnr-ice40** is the place-and-route tool. It takes the netlist from Yosys and decides where the logic should physically live inside the FPGA and how the internal routing wires should connect it.

Example command:

```bash
nextpnr-ice40 \
  --up5k \
  --package sg48 \
  --json build/top.json \
  --pcf pins.pcf \
  --asc build/top.asc
```

What it needs:

- `build/top.json`: synthesized netlist from Yosys
- `pins.pcf`: physical pin constraints
- `--up5k`: selects the iCE40UP5K device family target
- `--package sg48`: selects the SG48 package used on many iCE40UP5K breakout boards

What it produces:

```text
build/top.asc
```

The `.asc` file is a text representation of the configured FPGA fabric.

---

### PCF pin constraint file

The `.pcf` file maps your top-level Verilog ports to physical FPGA package pins.

Example:

```pcf
set_io clk 35
set_io led 39
```

This means:

```text
Verilog port clk -> FPGA physical pin 35
Verilog port led -> FPGA physical pin 39
```

This file is board-specific. If the PCF is wrong, the build may succeed but the board will appear not to work, or you may drive the wrong pin.

---

### icepack

**icepack** converts the `.asc` file from nextpnr into a binary bitstream that can be programmed into the FPGA or SPI flash.

Example command:

```bash
icepack build/top.asc build/top.bin
```

What it produces:

```text
build/top.bin
```

---

### iceprog

**iceprog** sends the bitstream to the board over the USB/FTDI programming interface.

Program SPI flash, persistent across power cycles:

```bash
iceprog build/top.bin
```

Program SRAM only, temporary until power is lost or the board is reset:

```bash
iceprog -S build/top.bin
```

For quick experiments, SRAM programming is convenient. For a design you want to boot automatically, program flash.

---

## 2. Recommended project structure

```text
my-ice40-project/
  Makefile
  pins.pcf
  src/
    top.v
  build/
    top.json
    top.asc
    top.bin
```

A minimal Makefile:

```makefile
TOP = top
DEVICE = up5k
PACKAGE = sg48

SRC = src/$(TOP).v
PCF = pins.pcf
BUILD = build

.PHONY: all prog sram clean

all: $(BUILD)/$(TOP).bin

$(BUILD):
	mkdir -p $(BUILD)

$(BUILD)/$(TOP).json: $(SRC) | $(BUILD)
	yosys -p "synth_ice40 -top $(TOP) -json $@" $(SRC)

$(BUILD)/$(TOP).asc: $(BUILD)/$(TOP).json $(PCF)
	nextpnr-ice40 --$(DEVICE) --package $(PACKAGE) --json $< --pcf $(PCF) --asc $@

$(BUILD)/$(TOP).bin: $(BUILD)/$(TOP).asc
	icepack $< $@

prog: $(BUILD)/$(TOP).bin
	iceprog $<

sram: $(BUILD)/$(TOP).bin
	iceprog -S $<

clean:
	rm -rf $(BUILD)
```

Build and program:

```bash
make
make sram    # temporary load
make prog    # persistent flash programming
```

---

## 3. macOS setup

### Option A: Homebrew packages (tested +)

Install Homebrew if you do not already have it:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Install the iCE40 tools:

```bash
brew update
brew install yosys nextpnr-ice40 icestorm
```

Check that the tools are available:

```bash
yosys -V
nextpnr-ice40 -V
icepack -h
iceprog --help
```

If your shell cannot find the tools, make sure Homebrew is on your PATH.

Apple Silicon default Homebrew path:

```bash
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
source ~/.zprofile
```

Intel Mac default Homebrew path:

```bash
echo 'eval "$(/usr/local/bin/brew shellenv)"' >> ~/.zprofile
source ~/.zprofile
```

### Option B: OSS CAD Suite

OSS CAD Suite is a prebuilt bundle containing Yosys, nextpnr, IceStorm, and related FPGA tools.

1. Download the macOS archive from the OSS CAD Suite releases page.
2. Extract it somewhere stable, for example:

```bash
mkdir -p ~/fpga-tools
# Move/extract oss-cad-suite into ~/fpga-tools/oss-cad-suite
```

3. Add it to your shell startup:

```bash
echo 'source ~/fpga-tools/oss-cad-suite/environment' >> ~/.zprofile
source ~/.zprofile
```

4. Verify:

```bash
yosys -V
nextpnr-ice40 --version
iceprog -h
```

### macOS programming notes

The board usually appears through an FTDI USB interface. If `iceprog` cannot find the board:

```bash
system_profiler SPUSBDataType | grep -i -A 10 ftdi
```

Try a different USB cable first; many mini-USB cables are charge-only. Also avoid USB hubs during first bring-up.

If macOS sees the FTDI device but `iceprog` fails, it may be a driver or permissions conflict. The Project IceStorm macOS notes are a good troubleshooting reference.

---

## 4. Linux setup

### Option A: OSS CAD Suite, recommended for consistency

Download the Linux archive from OSS CAD Suite releases, extract it, and source its environment script.

Example:

```bash
mkdir -p ~/fpga-tools
cd ~/fpga-tools
# Download the appropriate oss-cad-suite Linux archive from GitHub releases.
# Example filename will vary by date and architecture.
tar -xzf oss-cad-suite-linux-x64-*.tgz
```

Add to your shell startup:

```bash
echo 'source ~/fpga-tools/oss-cad-suite/environment' >> ~/.bashrc
source ~/.bashrc
```

Verify:

```bash
yosys -V
nextpnr-ice40 --version
iceprog -h
```

### Option B: Distribution packages

On some Linux distributions, the tools are available through the package manager.

Debian/Ubuntu example:

```bash
sudo apt update
sudo apt install yosys nextpnr-ice40 fpga-icestorm
```

Package names can vary by distribution and release. If your distro packages are old or missing `nextpnr-ice40`, use OSS CAD Suite instead.

### Linux USB permissions

If `iceprog` only works with `sudo`, you likely need a udev rule for the FTDI programmer.

First inspect the USB device:

```bash
lsusb
```

FTDI devices commonly use vendor ID `0403`, but confirm what your board reports.

Create a udev rule:

```bash
sudo tee /etc/udev/rules.d/53-lattice-ftdi.rules > /dev/null <<'RULE'
SUBSYSTEM=="usb", ATTR{idVendor}=="0403", MODE="0666", GROUP="plugdev"
RULE

sudo udevadm control --reload-rules
sudo udevadm trigger
```

Then unplug and replug the board.

---

## 5. Windows setup

### Option A: OSS CAD Suite for Windows

This is the simplest native Windows route.

1. Download the Windows x64 OSS CAD Suite archive from the releases page.
2. Extract it, for example to:

```text
C:\fpga-tools\oss-cad-suite
```

3. Start a configured shell using:

```text
C:\fpga-tools\oss-cad-suite\start.bat
```

Or configure an existing shell by running:

```text
C:\fpga-tools\oss-cad-suite\environment.bat
```

Verify in that shell:

```bat
yosys -V
nextpnr-ice40 --version
iceprog -h
```

Build example:

```bat
yosys -p "synth_ice40 -top top -json build/top.json" src/top.v
nextpnr-ice40 --up5k --package sg48 --json build/top.json --pcf pins.pcf --asc build/top.asc
icepack build/top.asc build/top.bin
iceprog build/top.bin
```

### Windows USB driver note

If synthesis and place-and-route work but `iceprog` cannot access the board, the issue is usually the USB driver bound to the FTDI interface. You may need a libusb-compatible driver for the relevant interface. Be careful not to replace drivers for unrelated devices.

A common Windows debugging path is:

1. Confirm the board appears in Device Manager.
2. Try a known data-capable USB cable.
3. Try a direct USB port, not a hub.
4. If needed, use a driver tool such as Zadig to bind the correct interface to WinUSB/libusb.

### Option B: WSL2

WSL2 is useful for building bitstreams, but USB programming from WSL requires extra USB passthrough setup. For a beginner setup, use native Windows OSS CAD Suite for programming, or build in WSL and copy the `.bin` file to Windows for `iceprog`.

---

## 6. Minimal blink design template

Create `src/top.v`:

```verilog
module top (
    input  wire clk,
    output wire led
);
    reg [23:0] counter = 24'd0;

    always @(posedge clk) begin
        counter <= counter + 1'b1;
    end

    assign led = counter[23];
endmodule
```

Create `pins.pcf` using the correct pins for your exact board.

Example placeholder only:

```pcf
# Replace these with verified pins from your board documentation.
set_io clk 35
set_io led 39
```

Build:

```bash
make
```

Program SRAM:

```bash
make sram
```

Program flash:

```bash
make prog
```

---

## 7. Sanity-check commands

Use these to verify your environment:

```bash
which yosys
which nextpnr-ice40
which icepack
which iceprog

yosys -V
nextpnr-ice40 --version
icepack -h
iceprog -h
```

Check USB device on macOS:

```bash
system_profiler SPUSBDataType | grep -i -A 10 ftdi
```

Check USB device on Linux:

```bash
lsusb
```

Check USB device on Windows:

```text
Device Manager -> Universal Serial Bus controllers / Ports / libusb devices
```

---

## 8. Common problems

### `iceprog: can't find iCE FTDI USB device`

Try:

- Use a known data-capable USB cable.
- Plug directly into the computer, not through a hub.
- Confirm the board is powered.
- Confirm the FTDI device appears in the OS USB/device list.
- On Linux, fix udev permissions.
- On Windows, check the USB driver.
- On macOS, check for FTDI driver conflicts.

### Build succeeds but LED does not blink

Likely causes:

- Wrong pin in `pins.pcf`.
- Wrong clock pin.
- Wrong assumption about active-high vs active-low LED.
- The selected LED is attached through special RGB/current-driver hardware rather than a plain GPIO.
- You programmed SRAM but then reset/power-cycled the board.

### nextpnr complains about package or device

For iCE40UP5K-SG48 boards, use:

```bash
nextpnr-ice40 --up5k --package sg48 ...
```

If your exact board uses a different package, change `--package` accordingly.

---

## 9. Useful references

- Yosys download / OSS CAD Suite install instructions: https://yosyshq.net/yosys/download.html
- OSS CAD Suite releases: https://github.com/YosysHQ/oss-cad-suite-build/releases
- Yosys documentation: https://yosyshq.readthedocs.io/projects/yosys/
- nextpnr repository: https://github.com/YosysHQ/nextpnr
- Project IceStorm documentation: https://prjicestorm.readthedocs.io/
- Project IceStorm GitHub: https://github.com/YosysHQ/icestorm
- Homebrew `icestorm` formula: https://formulae.brew.sh/formula/icestorm
- Homebrew `nextpnr-ice40` formula: https://formulae.brew.sh/formula/nextpnr-ice40
- Lattice Radiant page, for official-tool comparison: https://www.latticesemi.com/en/Products/DesignSoftwareAndIP/FPGAandLDS/Radiant

---

## 10. Suggested next steps for your HackRF/Raspberry Pi project

After blink works, do these in order:

1. Toggle a header pin and observe it with a logic analyzer or oscilloscope.
2. Implement UART TX from FPGA to computer/Pi.
3. Implement SPI slave on the FPGA and SPI master on the Raspberry Pi.
4. Send bytes from Pi to FPGA and display them on LEDs.
5. Add a small accumulator or moving average block.
6. Feed low-rate IQ-like sample pairs from the Pi to the FPGA.
7. Implement `power = I*I + Q*Q` and threshold detection.
8. Return event flags or power estimates back to the Pi.

That path gets you from basic FPGA bring-up to a real RF feature-extraction coprocessor.
