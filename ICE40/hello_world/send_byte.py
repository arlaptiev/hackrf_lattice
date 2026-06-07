#!/usr/bin/env python3
import argparse
import glob


def parse_byte(value: str) -> int:
    # Supports decimal (e.g. 65), hex (e.g. 0x41), or single char (e.g. A).
    if len(value) == 1 and not value.isdigit():
        parsed = ord(value)
    else:
        parsed = int(value, 0)

    if parsed < 0 or parsed > 255:
        raise argparse.ArgumentTypeError("byte must be in range 0..255")
    return parsed


def list_candidate_ports() -> list[str]:
    return sorted(glob.glob("/dev/cu.*") + glob.glob("/dev/tty.*"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Send one byte to iCE40 UART receiver")
    parser.add_argument(
        "port", nargs="?", help="Serial device, e.g. /dev/cu.usbserial-101"
    )
    parser.add_argument(
        "byte",
        nargs="?",
        type=parse_byte,
        help="Byte to send: 0x00..0xFF, decimal, or single char",
    )
    parser.add_argument(
        "--baud", type=int, default=115200, help="UART baud rate (default: 115200)"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List candidate serial ports and exit",
    )
    args = parser.parse_args()

    if args.list:
        ports = list_candidate_ports()
        if not ports:
            print("No serial ports found")
        else:
            print("Available serial ports:")
            for port in ports:
                print(port)
        return

    if args.port is None or args.byte is None:
        parser.error("port and byte are required unless --list is used")

    try:
        import serial  # pyserial
    except ImportError as exc:
        raise SystemExit("pyserial is required: pip install pyserial") from exc

    try:
        with serial.Serial(args.port, args.baud, timeout=1) as ser:
            payload = bytes([args.byte])
            ser.write(payload)
    except serial.SerialException as exc:
        print(f"Error opening serial port: {exc}")
        ports = list_candidate_ports()
        if ports:
            print("\nDetected ports:")
            for port in ports:
                print(port)
        raise SystemExit(1)

    print(f"Sent 0x{args.byte:02X} to {args.port} @ {args.baud} baud")


if __name__ == "__main__":
    main()
