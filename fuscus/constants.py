#!/usr/bin/env python3
"""Constants and hardware definitions for Fuscus."""

#
# Copyright 2015 Andrew Errington
#
# This file is part of BrewPi.
#
# BrewPi is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# BrewPi is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with BrewPi.  If not, see <http://www.gnu.org/licenses/>.
#

import argparse
import configparser

import EepromManager
import Menu
import door
import lcd
import piLink
import relay
import rotaryEncoder
import tempControl
import piSerialToNet

# LCD Hardware Modules
from lcd_hardware import pcd8544
from lcd_hardware import lcd2004_i2c

parser = argparse.ArgumentParser()
parser.add_argument('--config', '-c',
                    nargs='?',
                    default='fuscus.ini',
                    help='configuration file name')

args = parser.parse_args()


config = configparser.ConfigParser()
config.read(args.config)  # TODO - Wrap this in a try/except block to catch DuplicateOptionErrors and the like

if 'network' in config:
    print("Using config file '%s'" % args.config)
else:
    print("Config file {} not present, or is malformed. Did you copy the sample ini file and edit it?".format(args.config))

calibration = configparser.ConfigParser()
calibration.read('calibrate.ini')
if 'offset' in calibration:
    print("Using calibration file 'calibrate.ini'")
else:
    print("No 'calibration.ini' file or no calibration values present.")

# Port for TCP/IP control FIXME: not implemented yet
networkPort = config['network'].getint('port', 25518)
print("Network port: %s" % networkPort)

# GPIO pins (board numbering: GPIO.setmode(GPIO.BOARD))

# Rotary encoder (3 GPIO + 3.3V & GND)
# Best pin for pushbutton is pin 5 as it has a 1.8k pull-up.
# Also used to restart from halt.
rotary = config['ui'].get('rotary', 'None')
if rotary == 'None' or rotary == '':
    rotary = None
    print("No rotary encoder specified.")

elif rotary == 'True':
    rotary_PB = config['ui'].getint('rotary_PB')
    rotary_A = config['ui'].getint('rotary_A')
    rotary_B = config['ui'].getint('rotary_B')

    print("Rotary encoder specified.")
    print("rotary_PB = %s, rotary_A = %s, rotary_B = %s" %
          (rotary_PB, rotary_A, rotary_B))

else:
    print("Rotary encoder information cannot be read from ini file.")
    rotary = None

# LCD module (Nokia 5110 screen/PCD8544 controller) (6 GPIO + 3.3V & GND)
lcd_module = config['ui'].get('lcd', 'None')
if lcd_module == 'None' or lcd_module == '':
    lcd_module = None
    LCD_hardware = None
    print("No LCD module specified.")

elif lcd_module == 'pcd8544':
    lcd_RST = config['ui'].getint('lcd_RST')
    lcd_DC = config['ui'].getint('lcd_DC')
    lcd_LED = config['ui'].get('lcd_LED', 'None')

    lcd_contrast = config['ui'].get('lcd_contrast', 185)

    if lcd_LED == 'None':
        lcd_LED = None
    else:
        lcd_LED = int(lcd_LED)

    # These three pins are fixed to the hardware SPI module.
    # The numbers here are for reference only, so we can see
    # which pins are in use.
    lcd_DIN = 19
    lcd_SCLK = 23
    lcd_SCE = 24

    print("Nokia 5110/PCD8544 LCD specified.")
    print("lcd_RST = %s, lcd_DC = %s, lcd_LED = %s" % (lcd_RST, lcd_DC, lcd_LED))

    # Initialize the LCD_hardware object to pass to our LCD object later
    LCD_hardware = pcd8544.pcd8544(DC=lcd_DC, RST=lcd_RST, LED=lcd_LED, contrast=lcd_contrast)

elif lcd_module == 'lcd2004_i2c':
    lcd_port = config['ui'].getint('lcd_port', 1)  # The i2c bus - 0 for original RasPi, 1 for all modern RasPis
    lcd_i2c_pin_reverse = config['ui'].getint('lcd_i2c_pin_reverse', 1)  # Used if we need a non-standard pinout from the i2c expander
    lcd_address_str = config['ui'].get('lcd_address', '0x27')  # The device address (hex)

    lcd_address = int(lcd_address_str, 0)  # Convert the string (hex) to an actual number

    print("LCD2004 /w I2C expander specified.")
    print("lcd_port = %s, lcd_address = %s, lcd_i2c_pin_reverse = %s" % (lcd_port, lcd_address_str, lcd_i2c_pin_reverse))

    # Initialize the LCD_hardware object to pass to our LCD object later
    LCD_hardware = lcd2004_i2c.lcd2004_i2c(addr=lcd_address, port=lcd_port, reverse=lcd_i2c_pin_reverse)

else:
    print("LCD module '%s' not recognised." % lcd_module)
    lcd_module = None
    LCD_hardware = None

# Buzzer (1 GPIO + GND)
# FIXME: Not implemented
buzzer_pin = 15

# Relay board (2x 240Vac 10A relays) (2 GPIO + 3.3V + 5V + GND)
relay_HOT = config['relay'].getint('hot')
invert_hot = config['relay'].getboolean('invert_hot')
relay_COLD = config['relay'].getint('cold')
invert_cold = config['relay'].getboolean('invert_cold')
print("Hot relay on pin %s (%s)" % (relay_HOT, 'inverted' if invert_hot else 'not inverted'))
print("Cold relay on pin %s (%s)" % (relay_COLD, 'inverted' if invert_cold else 'not inverted'))

# One-wire bus (implemented by external system) (1 GPIO + 3.3V + GND)
one_wire = 7  # This number is for reference only

# One-wire sensor IDs
ID_fridge = config['sensors'].get('fridge')
ID_beer = config['sensors'].get('beer')
ID_ambient = config['sensors'].get('ambient')

fridgeCalibrationOffset = 0.0
beerCalibrationOffset = 0.0
ambientCalibrationOffset = 0.0

if not (ID_fridge):
    raise ValueError("1-wire address of fridge not specified in 'fuscus.ini'.")

if ID_beer == '':
    ID_beer = None

if ID_ambient == '':
    ID_ambient = None

if 'offset' in calibration:
    fridgeCalibrationOffset = calibration['offset'].getfloat(ID_fridge,0.0)
    if ID_beer:
        beerCalibrationOffset = calibration['offset'].getfloat(ID_beer,0.0)
    if ID_ambient:
        ambientCalibrationOffset = calibration['offset'].getfloat(ID_ambient,0.0)

print("Fridge sensor : %-15s (%+.2f)"%(ID_fridge,fridgeCalibrationOffset))
print("Beer sensor   : %-15s (%+.2f)"%(ID_beer,beerCalibrationOffset))
print("Ambient sensor: %-15s (%+.2f)"%(ID_ambient,ambientCalibrationOffset))

# Door (1 GPIO + GND)
# Best pin for this is pin 3 as it has a 1.8k pull-up on board
door_pin = config['door'].getint('pin')
if door_pin == '':
    door_pin = None

door_open_state = config['door'].getboolean('open_state', True)

if door_pin:
    print("Door switch on pin %s, open state %s" % (door_pin, door_open_state))
else:
    print("No door switch.")

# Unused GPIOs for reference
ser_TX = 8
ser_RX = 10
free_2 = 26

# Backlight control
# FIXME Unused
BACKLIGHT_AUTO_OFF_SECONDS = 120
BACKLIGHT_DIM_SECONDS = 30

BACKLIGHT_BRIGHT_LEVEL = 50
BACKLIGHT_DIM_LEVEL = 20

# Global objects for our hardware devices
DOOR = door.door(door_pin, door_open_state)

if rotary is not None:
    encoder = rotaryEncoder.rotaryEncoder(rotary_A, rotary_B, rotary_PB)
else:
    encoder = rotaryEncoder.rotaryEncoder(0, 0, 0, dummy=True)

encoder.start()

heater = relay.relay(relay_HOT, invert=invert_hot)
cooler = relay.relay(relay_COLD, invert=invert_cold)


# Nokia LCD has 17 chars by 6 lines, but original display and web display
# show 20 chars by 4 lines, so make a buffer at least that big.
LCD = lcd.lcd(lines=6, chars=20, hardware=LCD_hardware)

tempControl = tempControl.tempController(ID_fridge, ID_beer, ID_ambient,
                                         cooler=cooler, heater=heater, door=DOOR)

# Set the temperature calibration offsets (if available)
# FIXME - This should be part of deviceManager & saved to/loaded from the eeprom
tempControl.fridgeSensor.calibrationOffset = fridgeCalibrationOffset
tempControl.beerSensor.calibrationOffset = beerCalibrationOffset
tempControl.ambientSensor.calibrationOffset = ambientCalibrationOffset

eepromManager = EepromManager.eepromManager(tempControl=tempControl)

piLink = piLink.piLink(tempControl=tempControl, path=config['port'].get('path'), eepromManager=eepromManager)
menu = Menu.Menu(encoder=encoder, tempControl=tempControl, piLink=piLink)

# Setting up network
if networkPort is not None:
    piSerialToNet = piSerialToNet.PiSerialToNet(networkPort, config['port'].get('path'))