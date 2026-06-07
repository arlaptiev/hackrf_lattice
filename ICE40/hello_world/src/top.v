module top (
    input  wire uart_rx,
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

    localparam integer CLOCK_HZ = 48000000;
    localparam integer BAUD_RATE = 115200;
    localparam integer CLKS_PER_BIT = CLOCK_HZ / BAUD_RATE;

    wire [7:0] rx_byte;
    wire       rx_valid;

    uart_rx #(
        .CLKS_PER_BIT(CLKS_PER_BIT)
    ) uart_rx_inst (
        .clk(clk_48mhz),
        .rx(uart_rx),
        .data(rx_byte),
        .data_valid(rx_valid)
    );

    reg [2:0] rgb_state = 3'b000;

    // Update RGB state only for command bytes 0x00..0x07.
    // This filters out random UART noise that can cause visible flicker.
    always @(posedge clk_48mhz) begin
        if (rx_valid) begin
            if (rx_byte[7:3] == 5'b00000) begin
                rgb_state <= rx_byte[2:0];
            end
        end
    end

    // Drive the onboard RGB LED through the UltraPlus current driver primitive.
    SB_RGBA_DRV #(
        .CURRENT_MODE("0b1"),
        .RGB0_CURRENT("0b000001"),
        .RGB1_CURRENT("0b000001"),
        .RGB2_CURRENT("0b000001")
    ) rgba_drv_inst (
        .CURREN(1'b1),
        .RGBLEDEN(1'b1),
        .RGB0PWM(rgb_state[0]),
        .RGB1PWM(rgb_state[1]),
        .RGB2PWM(rgb_state[2]),
        .RGB0(rgb0),
        .RGB1(rgb1),
        .RGB2(rgb2)
    );
endmodule

module uart_rx #(
    parameter integer CLKS_PER_BIT = 417
) (
    input  wire       clk,
    input  wire       rx,
    output reg  [7:0] data = 8'h00,
    output reg        data_valid = 1'b0
);
    localparam [1:0] STATE_IDLE  = 2'd0;
    localparam [1:0] STATE_START = 2'd1;
    localparam [1:0] STATE_DATA  = 2'd2;
    localparam [1:0] STATE_STOP  = 2'd3;

    reg [1:0] state = STATE_IDLE;

    // Two-flop synchronizer for asynchronous UART input.
    reg [1:0] rx_sync = 2'b11;
    wire rx_bit = rx_sync[1];

    reg [15:0] clk_count = 16'd0;
    reg [2:0]  bit_index = 3'd0;
    reg [7:0]  shift_reg = 8'h00;

    always @(posedge clk) begin
        rx_sync <= {rx_sync[0], rx};
        data_valid <= 1'b0;

        case (state)
            STATE_IDLE: begin
                clk_count <= 16'd0;
                bit_index <= 3'd0;
                if (rx_bit == 1'b0) begin
                    state <= STATE_START;
                end
            end

            STATE_START: begin
                if (clk_count == (CLKS_PER_BIT / 2)) begin
                    clk_count <= 16'd0;
                    if (rx_bit == 1'b0) begin
                        state <= STATE_DATA;
                    end else begin
                        state <= STATE_IDLE;
                    end
                end else begin
                    clk_count <= clk_count + 16'd1;
                end
            end

            STATE_DATA: begin
                if (clk_count == (CLKS_PER_BIT - 1)) begin
                    clk_count <= 16'd0;
                    shift_reg[bit_index] <= rx_bit;

                    if (bit_index == 3'd7) begin
                        bit_index <= 3'd0;
                        state <= STATE_STOP;
                    end else begin
                        bit_index <= bit_index + 3'd1;
                    end
                end else begin
                    clk_count <= clk_count + 16'd1;
                end
            end

            STATE_STOP: begin
                if (clk_count == (CLKS_PER_BIT - 1)) begin
                    clk_count <= 16'd0;
                    state <= STATE_IDLE;
                    data <= shift_reg;
                    data_valid <= 1'b1;
                end else begin
                    clk_count <= clk_count + 16'd1;
                end
            end

            default: begin
                state <= STATE_IDLE;
            end
        endcase
    end
endmodule
