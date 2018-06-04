#!/usr/bin/python3

'''
GPIO connected to IOT relay. (https://www.iotrelay.com)
- GPIO24 (pin 18) to relay +
- GND (pin 20) to relay -

To continue running the process after logging out of ssh, stop this process using
Ctrl+Z or with 'kill -s SIGSTOP <pid>'. After that, run the following (assuming that
this is the only job being run; otherwise, change the %1):

$ disown -h %1
$ bg %1
$ logout

The best way to kill the process is to run 'kill -s SIGINT <pid>', since the code below
can handle this signal to exit gracefully. You can find the process ID in the first line
of the log file, or by running 'ps -x | grep python'.
'''

import sys, os, subprocess
import datetime, calendar
import pause
import RPi.GPIO as GPIO
import signal
import json

# Set up GPIO using BCM numbering
GPIO.setmode(GPIO.BCM)
GPIO.setup(24, GPIO.OUT)
GPIO.output(24, GPIO.LOW)

def signal_handler(signal, frame):
    GPIO.cleanup()
    with open(Waterer.log_file, 'a') as f:
        f.write( '[' + str(datetime.datetime.now()) + '] Quit\n' )
    sys.exit(0)

def get_timestamp():
    return '[' + str(datetime.datetime.now()) + '] '

# Set SIGINT to run the signal_handler function
signal.signal(signal.SIGINT, signal_handler)
    
class Waterer:

    # Numbers corresponding to each weekday
    weekdays = {
        'monday': 0,
        'tuesday': 1,
        'wednesday': 2,
        'thursday': 3,
        'friday': 4,
        'saturday': 5,
        'sunday': 6,
    }
    
    # Settings file
    settings_file = 'settings.json'
    
    # Log file
    log_file = 'waterer.log'

    # Default seconds to spend watering (replaces 'watering_time')
    default_watering_time = datetime.timedelta(seconds=8)

    # Default days of the week to water
    default_watering_days = ['Tuesday', 'Saturday']

    # Default hour at which to water the plant
    default_watering_hour = 12

    def __init__(self, overwrite_log = True):
        self.read_settings()

        now = datetime.datetime.today()
        self.date = self.get_next_watering_date(datetime.datetime(now.year, now.month, now.day, now.hour))

        if overwrite_log:
            with open(Waterer.log_file, 'w') as f: pass

    def get_next_watering_date(self, date):
        '''
        Returns the next date that the plant should be watered on
        '''
        # Get the day that is closest to now
        ts = [Waterer.weekdays[d] for d in self.watering_days]
        delta = min([t - date.weekday() + 7 * (date.weekday() >= t and date.hour >= self.watering_hour) for t in ts])

        # Return date object corresponding to the closest day
        return datetime.datetime(date.year, date.month, date.day, self.watering_hour) + datetime.timedelta(days=delta)

    def read_settings(self):
        '''
        Reads the settings file to set environment variables.
        '''
        try:
            # Remove old settings file
            subprocess.run( ['rm', self.settings_file] )

            # Download new settings file off GitHub
            subprocess.run( ['wget', 'https://raw.githubusercontent.com/wshand/rpi-watering/master/' + Waterer.settings_file] )
            with open(Waterer.settings_file, 'r') as f:
                settings = json.load(f)

            # Amount of time to water the plant
            self.watering_time = datetime.timedelta(seconds=int(settings['watering_time']))

            # Hour at which to water the plant
            self.watering_hour = int(settings['watering_hour'])
            assert 0 <= self.watering_hour <= 23

            # Parse the days on which the plant should be watered
            self.watering_days = settings['watering_days'].lower().replace(' ', '').split(',')
            assert set(self.watering_days) <= set(Waterer.weekdays.keys())
        except Exception as ex:
            # Set everything to the default; write error to the default log file
            self.watering_time = Waterer.default_watering_time
            self.days          = Waterer.default_days
            self.watering_hour = Waterer.default_watering_hour

            with open(Waterer.log_file, 'a') as f:
                f.write( get_timestamp() + str(ex) + '\n' )
                f.write( get_timestamp() + 'Unable to read ' + Waterer.settings_file + '; using defaults\n' )

    def water_loop(self):
        '''
        Controls the plant watering system.
        '''
        # Write initial message for starting the watering loop
        with open(Waterer.log_file, 'a') as f:
            f.write( get_timestamp() + 'Started; process PID is ' + str(os.getpid()) + '\n' )

            # Start watering loop
            while True:
                self.date = self.get_next_watering_date(datetime.datetime.now())
                f.write( get_timestamp() + 'Next session on ' +
                         calendar.day_name[self.date.weekday()] + ' ' + str(self.date) + '\n' )
                f.flush(); os.fsync(f.fileno())
                
                # Wait until we're ready to water the plant
                pause.until(self.date)

                # Update the settings
                self.read_settings()
            
                # Start watering
                GPIO.output(24, GPIO.HIGH)
                f.write( get_timestamp() + 'Started watering at ' + str(datetime.datetime.today()) + '; ' )
                pause.until(datetime.datetime.today() + self.watering_time)

                # Stop watering
                GPIO.output(24, GPIO.LOW)
                f.write( 'stopped at ' + str(datetime.datetime.today()) + '\n' )

'''
MAIN SCRIPT
'''
# Create the bot
bot = Waterer()

# Initiate the watering loop. If there's an error, output it to the error log
try:
    bot.water_loop()
except Exception as ex:
    with open(Waterer.default_log_file, 'a') as f:
        f.write( get_timestamp() + str(ex) + '\n' )
        f.write( get_timestamp() + 'Error; exiting.\n' )
    GPIO.cleanup()
    raise ex