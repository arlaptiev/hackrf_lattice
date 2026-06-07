TOP = top
DEVICE = up5k
PACKAGE = sg48

SRC = src/$(TOP).v \
      $(wildcard src/include/*.v)

PCF = pins.pcf
BUILD = build

.PHONY: all synth pnr bitstream sram prog clean

all: $(BUILD)/$(TOP).bin

$(BUILD):
	mkdir -p $(BUILD)

$(BUILD)/$(TOP).json: $(SRC) | $(BUILD)
	yosys -p "synth_ice40 -top $(TOP) -json $@" $(SRC)

$(BUILD)/$(TOP).asc: $(BUILD)/$(TOP).json $(PCF)
	nextpnr-ice40 --$(DEVICE) --package $(PACKAGE) --json $< --pcf $(PCF) --asc $@

$(BUILD)/$(TOP).bin: $(BUILD)/$(TOP).asc
	icepack $< $@

synth: $(BUILD)/$(TOP).json

pnr: $(BUILD)/$(TOP).asc

bitstream: $(BUILD)/$(TOP).bin

sram: $(BUILD)/$(TOP).bin
	iceprog -S $<

prog: $(BUILD)/$(TOP).bin
	iceprog $<

clean:
	rm -rf $(BUILD)