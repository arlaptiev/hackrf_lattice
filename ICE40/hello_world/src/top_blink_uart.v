module top_blink_uart (
    input  wire uart_rx,
    output wire rgb0,
    output wire rgb1,
    output wire rgb2
);

    // iCE40UP5K internal high-frequency oscillator: 24 MHz.
    wire clk;

    SB_HFOSC #(
        .CLKHF_DIV("0b01")
    ) hfosc_inst (
        .CLKHFPU(1'b1),
        .CLKHFEN(1'b1),
        .CLKHF(clk)
    );

    localparam integer CLOCK_HZ  = 24_000_000;
    localparam integer BAUD_RATE = 115_200;

    localparam integer TOGGLE_CLKS   = CLOCK_HZ;
    localparam integer RX_FLASH_CLKS = 6_000_000; // 0.25 s at 24 MHz

    // ------------------------------------------------------------------------
    // UART RX
    // ------------------------------------------------------------------------

    wire       uart_rx_break;
    wire       rx_valid;
    wire [7:0] rx_byte;

    uart_rx #(
        .BIT_RATE     (BAUD_RATE),
        .CLK_HZ       (CLOCK_HZ),
        .PAYLOAD_BITS (8),
        .STOP_BITS    (1)
    ) uart_rx_inst (
        .clk           (clk),
        .resetn        (1'b1),        // Tie high if you do not have a reset pin
        .uart_rxd      (uart_rx),
        .uart_rx_en    (1'b1),
        .uart_rx_break (uart_rx_break),
        .uart_rx_valid (rx_valid),
        .uart_rx_data  (rx_byte)
    );

    // ------------------------------------------------------------------------
    // LED blink and UART color command logic
    // ------------------------------------------------------------------------

    reg [2:0]  rgb_color        = 3'b001;
    reg [25:0] blink_counter    = 26'd0;
    reg        blink_on         = 1'b0;
    reg [23:0] rx_flash_counter = 24'd0;

    // Toggle once per second: 1s ON, 1s OFF.
    always @(posedge clk) begin
        if (blink_counter == TOGGLE_CLKS - 1) begin
            blink_counter <= 26'd0;
            blink_on <= ~blink_on;
        end else begin
            blink_counter <= blink_counter + 26'd1;
        end
    end

    // Accept color command bytes 0x00..0x07 from host.
    // Trigger white flash only on explicit debug byte 0x55.
    always @(posedge clk) begin
        if (rx_valid) begin
            if (rx_byte[7:3] == 5'b00000) begin
                rgb_color <= rx_byte[2:0];
            end else if (rx_byte == 8'h55) begin
                rx_flash_counter <= RX_FLASH_CLKS - 1;
            end
        end else if (rx_flash_counter != 24'd0) begin
            rx_flash_counter <= rx_flash_counter - 24'd1;
        end
    end

    wire [2:0] rgb_pwm = blink_on ? rgb_color : 3'b000;
    wire [2:0] rgb_out = (rx_flash_counter != 24'd0) ? 3'b111 : rgb_pwm;

    // ------------------------------------------------------------------------
    // iCE40 RGB LED driver
    // ------------------------------------------------------------------------

    SB_RGBA_DRV #(
        .CURRENT_MODE("0b1"),
        .RGB0_CURRENT("0b000001"),
        .RGB1_CURRENT("0b000001"),
        .RGB2_CURRENT("0b000001")
    ) rgba_drv_inst (
        .CURREN   (1'b1),
        .RGBLEDEN (1'b1),

        .RGB0PWM  (rgb_out[0]),
        .RGB1PWM  (rgb_out[1]),
        .RGB2PWM  (rgb_out[2]),

        .RGB0     (rgb0),
        .RGB1     (rgb1),
        .RGB2     (rgb2)
    );

endmodule