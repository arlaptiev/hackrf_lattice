module top_blink (
    output wire rgb0,
    output wire rgb1,
    output wire rgb2
);
    // iCE40UP5K internal high-frequency oscillator (48 MHz).
    wire clk_48mhz;
    SB_HFOSC #(
        .CLKHF_DIV("0b00")
    ) hfosc_inst (
        .CLKHFPU(1'b1),
        .CLKHFEN(1'b1),
        .CLKHF(clk_48mhz)
    );

    // Toggle once per second: 1s ON, 1s OFF.
    localparam integer TOGGLE_CLKS = 48000000;
    reg [25:0] counter = 26'd0;
    reg led_on = 1'b0;

    always @(posedge clk_48mhz) begin
        if (counter == TOGGLE_CLKS - 1) begin
            counter <= 26'd0;
            led_on <= ~led_on;
        end else begin
            counter <= counter + 26'd1;
        end
    end

    SB_RGBA_DRV #(
        .CURRENT_MODE("0b1"),
        .RGB0_CURRENT("0b000001"),
        .RGB1_CURRENT("0b000001"),
        .RGB2_CURRENT("0b000001")
    ) rgba_drv_inst (
        .CURREN(1'b1),
        .RGBLEDEN(1'b1),
        .RGB0PWM(led_on),
        .RGB1PWM(led_on),
        .RGB2PWM(led_on),
        .RGB0(rgb0),
        .RGB1(rgb1),
        .RGB2(rgb2)
    );
endmodule
