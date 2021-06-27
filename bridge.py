#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import paho.mqtt.client as mqtt
import subprocess
import time
import re
import threading
import os

# Default configuration
config = {
    'mqtt': {
        'broker': '192.168.1.1',
        'devicename': 'cec-mqtt',
        'port': 1883,
        'prefix': 'media/theatre_1',
        'user': os.environ.get('MQTT_USER'),
        'password': os.environ.get('MQTT_PASSWORD'),
        'tls': 0,
    },
    'cec': {
        'id': 1,
        'port': 'RPI',
        'devices': '0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15',
    },
}

device_names = {'0': 'TV'}

def set_device_name(logical_address, name):
    logical_address = str(logical_address)
    for key, value in device_names.items():
        if value == name and not key == logical_address:
            del device_names[key]
    if name == "LivingRoomTv":
        name = "Chromecast"
    device_names[logical_address] = name
    
def get_device_name(logical_address):
    return device_names[str(logical_address)]

active_source_id = None
should_refresh_power_status = False

def mqtt_on_connect(client, userdata, flags, rc):
    """@type client: paho.mqtt.client """

    print("Connection returned result: " + str(rc))

    # Subscribe to CEC commands
    client.subscribe([
        (config['mqtt']['prefix'] + '/cec/cmd', 0),
        (config['mqtt']['prefix'] + '/cec/+/cmd', 0),
        (config['mqtt']['prefix'] + '/cec/+/set', 0),
        (config['mqtt']['prefix'] + '/cec/tx', 0)
    ])

    # Publish birth message
    client.publish(config['mqtt']['prefix'] + '/bridge/status', 'online', qos=1, retain=True)


def mqtt_on_message(client, userdata, message):
    """@type client: paho.mqtt.client """

    try:

        # Decode topic
        cmd = message.topic.replace(config['mqtt']['prefix'], '').strip('/')
        print("Command received: %s (%s)" % (cmd, message.payload))

        split = cmd.split('/')

        if split[0] == 'cec':

            if split[1] == 'cmd':

                action = message.payload.decode()

                if action == 'mute':
                    cec_client.AudioMute()
                    cec_send('71', id=5)
                    return

                if action == 'unmute':
                    cec_client.AudioUnmute()
                    cec_send('71', id=5)
                    return

                if action == 'voldown':
                    cec_client.VolumeDown()
                    cec_send('71', id=5)
                    return

                if action == 'volup':
                    cec_client.VolumeUp()
                    cec_send('71', id=5)
                    return
                
                if action == 'standby':
                    cec_send('36', id=15)
                    return

                raise Exception("Unknown command (%s)" % action)

            if split[1] == 'tx':
                commands = message.payload.decode().split(',')
                for command in commands:
                    print(" Sending raw: %s" % command)
                    cec_send(command)
                return

            if split[2] == 'set':

                if split[1] == 'volume':
                    action = int(message.payload.decode())

                    if action >= 0 and action <= 100:
                        volume = cec_volume()

                        # Attempt to set the correct volume, but try to avoid a never-ending loop due to rounding issues
                        attempts = 0
                        while volume != action and attempts <= 10:
                            diff = abs(volume - action)

                            # Run a bulk of vol up/down actions to close a large gap at first (inaccurate, but quick)
                            if diff >= 10:
                                for _ in range(round(diff / 2.5)):
                                    if volume < action:
                                        cec_client.VolumeUp()
                                    else:
                                        cec_client.VolumeDown()

                            # Set the volume precisely after the bulk operations, try to avoid an endless loop due to rounding
                            else:
                                if volume < action:
                                    cec_client.VolumeUp()
                                else:
                                    cec_client.VolumeDown()

                            # Refresh the volume levels and wait for the value to return before each loop
                            cec_send('71', id=5)
                            time.sleep(.2)
                            volume = cec_volume()
                            attempts += 1
                        return

                    raise Exception("Unknown command (%s)" % action)

            if split[2] == 'cmd':

                action = message.payload.decode()

                if action == 'on':
                    id = int(split[1])
                    if id == 0:
                        cec_send('04', id=id)
                    else:
                        cec_send('44:6D', id=id)
                    should_refresh_power_status = True
                    return

                if action == 'standby':
                    id = int(split[1])
                    cec_send('36', id=id)
                    cec_refresh_power_status()
                    return

                raise Exception("Unknown command (%s)" % action)

    except Exception as e:
        print("Error during processing of message: ", message.topic, message.payload, str(e))


def mqtt_send(topic, value, retain=False):
    mqtt_client.publish(topic, value, retain=retain)

def mqtt_send_power_status(id, power):
    if power == '00':
        power = 'on'
        if id == 0:
            #resend active source
            pass
    elif power == '02':
        power = 'turning on...'
        cec_refresh_power_status()
    elif power == '03':
        power = 'turning off...'
        cec_refresh_power_status()
    else:
        power = 'standby'
    try:
        mqtt_send(config['mqtt']['prefix'] + '/cec/' + get_device_name(id) + '/power', power, True)
    except KeyError as e:
        cec_request_name(id)


def cec_on_message(level, time, message):
    # Send raw command to mqtt
    m = re.search('>> ([0-9a-f:]+)', message)
    if m:
        mqtt_send(config['mqtt']['prefix'] + '/cec/rx', m.group(1))

    # Report Power Status
    m = re.search('>> ([0-9a-f])[0-9a-f]:90:([0-9a-f]{2})', message)
    if m:
        id = int(m.group(1), 16)
        mqtt_send_power_status(id, m.group(2))
        if not power and id == active_source_id:
            mqtt_send(config['mqtt']['prefix'] + '/cec/active_source', "none", False)
            active_source_id = None
        return

    # Report OSD Name
    m = re.search('>> ([0-9a-f])[0-9a-f]:47:([0-9a-f]{2}(:[0-9a-f]{2})*)', message)
    if m:
        id = int(m.group(1), 16)
        name =  bytearray.fromhex(m.group(2).replace(':','')).decode()
        set_device_name(id, name)
        try:
            mqtt_send(config['mqtt']['prefix'] + '/cec/' + get_device_name(id) + '/logical_address', id, True)
        except KeyError as e:
            cec_request_name(id)
        cec_interrogate(id)
        return

    # Device Vendor ID
    m = re.search('>> ([0-9a-f])[0-9a-f]:87', message)
    if m:
        id = int(m.group(1), 16)
        vendor = bytearray.fromhex(m.group(2).replace(':','')).decode()
        try:
            mqtt_send(config['mqtt']['prefix'] + '/cec/' + get_device_name(id) + '/vendor', vendor, True)
        except KeyError as e:
            cec_request_name(id)
        return

    # Report Physical Address
    m = re.search('>> ([0-9a-f])[0-9a-f]:84:([0-9a-f]{2}:[0-9a-f]{2})[0-9a-f:]+', message)
    if m:
        id = int(m.group(1), 16)
        address = '.'.join(list(m.group(2).replace(':','')))
        try:
            mqtt_send(config['mqtt']['prefix'] + '/cec/' + get_device_name(id) + '/physical_address', address, True)
        except KeyError as e:
            cec_request_name(id)
        return

    # Report Audio Status
    m = re.search('>> ([0-9a-f])[0-9a-f]:7a:([0-9a-f]{2})', message)
    if m:
        volume = None
        mute = None

        audio_status = int(m.group(2), 16)
        if audio_status <= 100:
            volume = audio_status
            mute = 'off'
        elif audio_status >= 128:
            volume = audio_status - 128
            mute = 'on'

        if isinstance(volume, int):
            mqtt_send(config['mqtt']['prefix'] + '/cec/volume', volume, False)
        if mute:
            mqtt_send(config['mqtt']['prefix'] + '/cec/mute', mute, False)
        return
    
    # Report Active Source
    m = re.search('>> ([0-9a-f])[0-9a-f]:82:([0-9a-f]{2}:[0-9a-f]{2})', message)
    if m:
        active_source_id = int(m.group(1), 16)
        try:
            get_device_name(active_source_id)
        except KeyError as e:
            cec_request_name(active_source_id)
            
        active_source = '.'.join(list(m.group(2).replace(':','')))
        if active_source == '0.0.0.0':
            active_source = 'none'
            active_source_id = None
        mqtt_send(config['mqtt']['prefix'] + '/cec/active_source', active_source, True)
        cec_refresh_power_status()
        return
    
        # Report Inactive Source
    m = re.search('>> ([0-9a-f])[0-9a-f]:9D:([0-9a-f]{2}:[0-9a-f]{2})', message)
    if m:
        active_source_id = int(m.group(1), 16)
        active_source = '.'.join(list(m.group(2).replace(':','')))
        mqtt_send(config['mqtt']['prefix'] + '/cec/active_source', "none", True)
        cec_refresh_power_status()
        return
        

def cec_volume():
    audio_status = cec_client.AudioStatus()
    if audio_status <= 100:
        return audio_status
    elif audio_status >= 128:
        return audio_status - 128


def cec_send(cmd, id=None):
    if id is None:
        cec_client.Transmit(cec_client.CommandFromString(cmd))
    else:
        cec_client.Transmit(cec_client.CommandFromString('1%s:%s' % (hex(id)[2:], cmd)))

def cec_refresh_power_status():
    time.sleep(2)
    print("Refreshing power status...")
    try:
        for id in config['cec']['devices'].split(','):
            cec_send('8F', id=int(id)) # Request Power Status

    except Exception as e:
        print("Error during refreshing: ", str(e))

def cec_interrogate(id):
    print("Scanning cec for id: " + str(id))
    try:
        cec_send('83', id=int(id)) # Request Physical Address
        cec_send('8F', id=int(id)) # Request Power Status
        cec_send('8C', id=int(id))
    except Exception as e:
        print("Error during refreshing: ", str(e))

def cec_scan():
    try:
        for id in config['cec']['devices'].split(','):
            cec_request_name(id)
        cec_send('71', id=5) # Request Mute Status and Volume Level
        cec_send('85', id=15) # Request Active Source

    except Exception as e:
        print("Error during refreshing: ", str(e))

def cec_request_name(id):
    cec_send('46', id=int(id)) # Request OSD Name


def cleanup():
    mqtt_client.loop_stop()
    mqtt_client.publish(config['mqtt']['prefix'] + '/bridge/status', 'offline', qos=1, retain=True)
    mqtt_client.disconnect()


try:
    ### Setup CEC ###
    print("Initialising CEC...")
    try:
        import cec

        cec_config = cec.libcec_configuration()
        cec_config.strDeviceName = "cec-mqtt"
        cec_config.bActivateSource = 0
        cec_config.deviceTypes.Add(cec.CEC_DEVICE_TYPE_RECORDING_DEVICE)
        cec_config.clientVersion = cec.LIBCEC_VERSION_CURRENT
        cec_config.SetLogCallback(cec_on_message)
        cec_client = cec.ICECAdapter.Create(cec_config)
        if not cec_client.Open(config['cec']['port']):
            raise Exception("Could not connect to cec adapter")
    except Exception as e:
        print("ERROR: Could not initialise CEC:", str(e))
        exit(1)

    ### Setup MQTT ###
    print("Initialising MQTT...")
    mqtt_client = mqtt.Client(config['mqtt']['devicename'])
    mqtt_client.on_connect = mqtt_on_connect
    mqtt_client.on_message = mqtt_on_message
    if config['mqtt']['user']:
        mqtt_client.username_pw_set(config['mqtt']['user'], password=config['mqtt']['password']);
    if int(config['mqtt']['tls']) == 1:
        mqtt_client.tls_set();
    mqtt_client.will_set(config['mqtt']['prefix'] + '/bridge/status', 'offline', qos=1, retain=True)
    mqtt_client.connect(config['mqtt']['broker'], int(config['mqtt']['port']), 60)
    mqtt_client.loop_start()
    
    cec_scan()
    cec_interrogate(0)
            
    print("Starting main loop...")
    while True:
        pass
except KeyboardInterrupt:
    cleanup()

except RuntimeError:
    cleanup()
