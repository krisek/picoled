import rp2
import network
import ubinascii
import machine
from machine import Pin, PWM
import urequests
import settings
import time
import socket
import json
import re


while True:
    try:
        # Set country to avoid possible errors
        rp2.country('DE')

        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        # If you need to disable powersaving mode
        # wlan.config(pm = 0xa11140)

        # See the MAC address in the wireless chip OTP
        mac = ubinascii.hexlify(network.WLAN().config('mac'),':').decode()
        print('mac = ' + mac)

        # Other things to query
        # print(wlan.config('channel'))
        # print(wlan.config('essid'))
        # print(wlan.config('txpower'))

        # Load login data from different file for safety reasons

        wlan.connect(settings.secrets['ssid'], settings.secrets['pw'])

        # Wait for connection with 10 second timeout
        timeout = 10
        while timeout > 0:
            if wlan.status() < 0 or wlan.status() >= 3:
                break
            timeout -= 1
            print('Waiting for connection...')
            time.sleep(1)

        # Define blinking function for onboard LED to indicate error codes    
        def blink_onboard_led(num_blinks):
            on_board_led = machine.Pin('LED', machine.Pin.OUT)
            for i in range(num_blinks):
                on_board_led.on()
                time.sleep(.2)
                on_board_led.off()
                time.sleep(.2)
            
        # Handle connection error
        # Error meanings
        # 0  Link Down
        # 1  Link Join
        # 2  Link NoIp
        # 3  Link Up
        # -1 Link Fail
        # -2 Link NoNet
        # -3 Link BadAuth

        wlan_status = wlan.status()
        blink_onboard_led(wlan_status)

        if wlan_status != 3:
            raise RuntimeError('Wi-Fi connection failed')
        else:
            print('Connected')
            status = wlan.ifconfig()
            print('ip = ' + status[0])
            
        # Function to load in html page    
        def get_html(html_name):
            with open(html_name, 'r') as file:
                html = file.read()
                
            return html

        def get_led_state():
            led_state = {'red': 0, 'green': 0, 'blue': 0}
            try:
                with open('led_state') as f:
                    ch_raw = ''.join(f.readlines())
                led_state = json.loads(ch_raw)
            except:
                pass
            return(led_state)

        # HTTP server with socket
        addr = socket.getaddrinfo('0.0.0.0', 9001)[0][-1]

        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(addr)
        s.listen(1)

        print('Listening on', addr)
        on_board_led = machine.Pin('LED', machine.Pin.OUT)

        #init colors

        leds = {
        'red': PWM(Pin(1)),
        'blue': PWM(Pin(2)),
        'green':  PWM(Pin(3)),
        }


        led_state = get_led_state()


        for color in leds:
            leds[color].freq(1000)
            leds[color].duty_u16(256*int(led_state[color]))

        colors = leds.keys();

        status = {
        'on': 100,
        'off': 0
        }

        # Listen for connections
        while True:
            try:
                cl, addr = s.accept()
                print('Client connected from', addr)
                r = cl.recv(1024)
                # print(r)
                
                r = str(r, 'utf-8')
                #print('=======\nRequest:\n')
                #print(r)
                #print('=======\n')
                led_on = r.find('?led=on')
                led_off = r.find('?led=off')
                print('led_on = ', led_on)
                print('led_off = ', led_off)
                if led_on > -1:
                    print('LED ON')
                    on_board_led.value(1)
                    
                if led_off > -1:
                    print('LED OFF')
                    on_board_led.value(0)

                sensor_temp = machine.ADC(4)
                conversion_factor = 3.3 / (65535)
                reading = sensor_temp.read_u16() * conversion_factor
                #temperature = 27 - (reading - 0.706)/0.001721
                temperature = 20 - (reading - 0.706)/0.001721

                if r.find('/set?') > -1:
                    print('setter called')
                    dc_in = {'red': 0, 'green': 0, 'blue': 0}
                    for key in leds:
                        color = re.search("{}=(\d+)".format(key), r)
                        #print(color)
                        if color:
                            #print(color.group(1))
                            dc_in[key] = min(int(color.group(1)),255)
                            dc_in[key] = str(max(int(dc_in[key]),0))
                            leds[key].duty_u16(256*int(dc_in[key]))
                    with open('led_state', 'w') as ch:
                        ch.write(json.dumps(dc_in))
                    cl.send('HTTP/1.0 200 OK\r\nContent-type: application/json\r\nAccess-Control-Allow-Origin: *\r\n\r\n')
                    response = json.dumps(dc_in).encode()
                    cl.send(response)
                    cl.close()           
                    
                elif r.find('/get') > -1:
                    print('getter called')
                    cl.send('HTTP/1.0 200 OK\r\nContent-type: application/json\r\nAccess-Control-Allow-Origin: *\r\n\r\n')
                    led_state = get_led_state()
                    led_state['temperature'] = temperature
                    response = json.dumps(led_state).encode()
                    cl.send(response)
                    cl.close()
                elif r.find('/update') > -1:
                    print('updating')
                    for file_to_update in ['index.html', 'main.py']:
                        response = urequests.get('https://raw.githubusercontent.com/krisek/picoled/main/' + file_to_update)
                        if(response.status_code == 200):
                            with open(file_to_update, 'w') as ch:
                                ch.write(response.content)
                        response.close()
                    
                    
                    cl.send('HTTP/1.0 200 OK\r\nContent-type: application/json\r\nAccess-Control-Allow-Origin: *\r\n\r\n')
                    response = json.dumps({'updated': True}).encode()
                    cl.send(response)
                    cl.close()
                    machine.reset()
                else:
                    print('showing index')

                    with open('index.html', 'r') as file:
                        response = file.read()
                    
                    cl.send('HTTP/1.0 200 OK\r\nContent-type: text/html\r\n\r\n')
                    cl.send(response)
                    cl.close()
                
            except OSError as e:
                cl.close()
                print('Connection closed')
    except Exception as e:
        if hasattr(e, 'message'):
            print(e.message)
        else:
            print(e)
        with open('last_error.txt', 'w') as ch:
            ch.write(e.__dict__)          
    time.sleep(5)
    
