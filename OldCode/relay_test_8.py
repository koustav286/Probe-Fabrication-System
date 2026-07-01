import lgpio
import time

VOLTAGE = 5  # (not used)

RELAY_PIN_1 = 17
RELAY_PIN_2 = 27
RELAY_PIN_3 = 22
RELAY_PIN_4 = 23
RELAY_PIN_5 = 26
RELAY_PIN_6 = 24
RELAY_PIN_7 = 16
RELAY_PIN_8 = 25

# Open GPIO chip
h = lgpio.gpiochip_open(0)

try:
    # Set all pins as output
    lgpio.gpio_claim_output(h, RELAY_PIN_1)
    lgpio.gpio_claim_output(h, RELAY_PIN_2)
    lgpio.gpio_claim_output(h, RELAY_PIN_3)
    lgpio.gpio_claim_output(h, RELAY_PIN_4)
    lgpio.gpio_claim_output(h, RELAY_PIN_5)
    lgpio.gpio_claim_output(h, RELAY_PIN_6)
    lgpio.gpio_claim_output(h, RELAY_PIN_7)
    lgpio.gpio_claim_output(h, RELAY_PIN_8)

    while True:
        # ---- ON SEQUENCE ----
        lgpio.gpio_write(h, RELAY_PIN_1, 1)
        print("Relay1 ON")
        time.sleep(2)

        lgpio.gpio_write(h, RELAY_PIN_2, 1)
        print("Relay2 ON")
        time.sleep(2)

        lgpio.gpio_write(h, RELAY_PIN_3, 1)
        print("Relay3 ON")
        time.sleep(2)

        lgpio.gpio_write(h, RELAY_PIN_4, 1)
        print("Relay4 ON")
        time.sleep(2)

        lgpio.gpio_write(h, RELAY_PIN_5, 1)
        print("Relay5 ON")
        time.sleep(2)

        lgpio.gpio_write(h, RELAY_PIN_6, 1)
        print("Relay6 ON")
        time.sleep(2)

        lgpio.gpio_write(h, RELAY_PIN_7, 1)
        print("Relay7 ON")
        time.sleep(2)

        lgpio.gpio_write(h, RELAY_PIN_8, 1)
        print("Relay8 ON")
        time.sleep(2)

        # ---- OFF SEQUENCE ----
        lgpio.gpio_write(h, RELAY_PIN_1, 0)
        print("Relay1 OFF")
        time.sleep(2)

        lgpio.gpio_write(h, RELAY_PIN_2, 0)
        print("Relay2 OFF")
        time.sleep(2)

        lgpio.gpio_write(h, RELAY_PIN_3, 0)
        print("Relay3 OFF")
        time.sleep(2)

        lgpio.gpio_write(h, RELAY_PIN_4, 0)
        print("Relay4 OFF")
        time.sleep(2)

        lgpio.gpio_write(h, RELAY_PIN_5, 0)
        print("Relay5 OFF")
        time.sleep(2)

        lgpio.gpio_write(h, RELAY_PIN_6, 0)
        print("Relay6 OFF")
        time.sleep(2)

        lgpio.gpio_write(h, RELAY_PIN_7, 0)
        print("Relay7 OFF")
        time.sleep(2)

        lgpio.gpio_write(h, RELAY_PIN_8, 0)
        print("Relay8 OFF")
        time.sleep(2)

except KeyboardInterrupt:
    print("\nProgram interrupted. Cleaning up...")

finally:
    lgpio.gpiochip_close(h)
    print("GPIO released and program exited.")
