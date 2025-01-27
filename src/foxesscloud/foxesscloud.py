##################################################################################################
"""
Module:   Fox ESS Cloud
Updated:  30 August 2023
By:       Tony Matthews
"""
##################################################################################################
# Code for getting and setting inverter data via the Fox ESS cloud web site, including
# getting forecast data from solcast.com.au and sending inverter data to pvoutput.org
##################################################################################################

version = "0.3.4"
debug_setting = 1

print(f"FoxESS-Cloud version {version}")

import os.path
import json
from datetime import datetime, timedelta
from copy import deepcopy
import requests
from requests.auth import HTTPBasicAuth
import hashlib
from random_user_agent.user_agent import UserAgent
from random_user_agent.params import SoftwareName, OperatingSystem
import math
import matplotlib.pyplot as plt

software_names = [SoftwareName.CHROME.value]
operating_systems = [OperatingSystem.WINDOWS.value, OperatingSystem.LINUX.value]
user_agent_rotator = UserAgent(software_names=software_names, operating_systems=operating_systems, limit=100)

##################################################################################################
##################################################################################################
# Fox ESS Cloud API Section
##################################################################################################
##################################################################################################

token = {'value': None, 'valid_from': None, 'valid_for': timedelta(hours=1).seconds, 'user_agent': None, 'lang': 'en'}

def query_date(d, offset = None):
    if d is not None and len(d) < 18:
        d += ' 00:00:00'
    t = datetime.now() if d is None else datetime.strptime(d, "%Y-%m-%d %H:%M:%S")
    if offset is not None:
        t += timedelta(days = offset)
    return {'year': t.year, 'month': t.month, 'day': t.day, 'hour': t.hour, 'minute': t.minute, 'second': t.second}

# global username and password settings
username = None
password = None

# login and get token if required. Check if token has expired and renew if required.
def get_token():
    global username, password, token, device_list, device, device_id, debug_setting
    time_now = datetime.now()
    if token['valid_from'] is not None:
        if (time_now - token['valid_from']).seconds <= token['valid_for']:
            if debug_setting > 1:
                print(f"token is still valid")
            return token['value']
    if debug_setting > 1:
        print(f"loading new token")
    device_list = None
    device = None
    token['user_agent'] = user_agent_rotator.get_random_user_agent()
    headers = {'User-Agent': token['user_agent'], 'lang': token['lang'], 'Connection': 'keep-alive'}
    if username is None or password is None or username == '<my.fox_username>' or password == 'my.fox_password':
        print(f"** please configure your Fox ESS Cloud username and password")
        return None
    credentials = {'user': username, 'password': hashlib.md5(password.encode()).hexdigest()}
    response = requests.post(url="https://www.foxesscloud.com/c/v0/user/login", headers=headers, data=json.dumps(credentials))
    if response.status_code != 200:
        print(f"** could not login to Fox ESS Cloud - check your username and password - got response code: {response.status_code}")
        return None
    result = response.json().get('result')
    if result is None:
        print(f"** no login result data")
        return None
    token['value'] = result.get('token')
    if token['value'] is None:
        print(f"** no token  in result data")
    token['valid_from'] = time_now
    return token['value']

##################################################################################################
# get user / access info
##################################################################################################

info = None

def get_info():
    global token, debug_setting, info
    if get_token() is None:
        return None
    if debug_setting > 1:
        print(f"getting access")
    headers = {'token': token['value'], 'User-Agent': token['user_agent'], 'lang': token['lang'], 'Connection': 'keep-alive'}
    response = requests.get(url="https://www.foxesscloud.com/c/v0/user/info", headers=headers)
    if response.status_code != 200:
        print(f"** get_info() got info response code: {response.status_code}")
        return None
    result = response.json().get('result')
    if result is None:
        print(f"** no info result")
        return None
    info = result
    response = requests.get(url="https://www.foxesscloud.com/c/v0/user/access", headers=headers)
    if response.status_code != 200:
        print(f"** get_info() got access response code: {response.status_code}")
        return None
    result = response.json().get('result')
    if result is None:
        print(f"** no access result")
        return None
    info['access'] = result['access']
    return info


##################################################################################################
# get list of sites
##################################################################################################

site_list = None
site = None

def get_site(name=None):
    global token, site_list, site, debug_setting
    if get_token() is None:
        return None
    if site is not None and name is None:
        return site
    if debug_setting > 1:
        print(f"getting sites")
    headers = {'token': token['value'], 'User-Agent': token['user_agent'], 'lang': token['lang'], 'Connection': 'keep-alive'}
    query = {'pageSize': 100, 'currentPage': 1, 'total': 0, 'condition': {'status': 0, 'contentType': 2, 'content': ''} }
    response = requests.post(url="https://www.foxesscloud.com/c/v1/plant/list", headers=headers, data=json.dumps(query))
    if response.status_code != 200:
        print(f"** get_sites() got response code: {response.status_code}")
        return None
    result = response.json().get('result')
    if result is None:
        print(f"** no site list result data")
        return None
    total = result.get('total')
    if total is None or total == 0 or total > 100:
        print(f"** invalid list of sites returned: {total}")
        return None
    site_list = result.get('plants')
    n = None
    if len(site_list) > 1:
        if name is not None:
            for i in range(len(site_list)):
                if site_list[i]['name'][:len(name)].upper() == name.upper():
                    n = i
                    break
        if n is None:
            print(f"\nget_site(): please provide a name from the list:")
            for s in site_list:
                print(f"Name={s['name']}")
            return None
    else:
        n = 0
    site = site_list[n]
    return site

##################################################################################################
# get list of data loggers
##################################################################################################

logger_list = None
logger = None

def get_logger(sn=None):
    global token, logger_list, logger, debug_setting
    if get_token() is None:
        return None
    if logger is not None and sn is None:
        return logger
    if debug_setting > 1:
        print(f"getting loggers")
    headers = {'token': token['value'], 'User-Agent': token['user_agent'], 'lang': token['lang'], 'Connection': 'keep-alive'}
    query = {'pageSize': 100, 'currentPage': 1, 'total': 0, 'condition': {'communication': 0, 'moduleSN': '', 'moduleType': ''} }
    response = requests.post(url="https://www.foxesscloud.com/c/v0/module/list", headers=headers, data=json.dumps(query))
    if response.status_code != 200:
        print(f"** get_logger() got response code: {response.status_code}")
        return None
    result = response.json().get('result')
    if result is None:
        print(f"** no logger list result data")
        return None
    total = result.get('total')
    if total is None or total == 0 or total > 100:
        print(f"** invalid list of loggers returned: {total}")
        return None
    logger_list = result.get('data')
    n = None
    if len(logger_list) > 1:
        if sn is not None:
            for i in range(len(logger_list)):
                if site_list[i]['moduleSN'][:len(sn)].upper() == sn.upper():
                    n = i
                    break
        if n is None:
            print(f"\nget_logger(): please provide a serial number from this list:")
            for l in logger_list:
                print(f"SN={l['moduleSN']}, Plant={l['plantName']}, StationID={l['stationID']}")
            return None
    else:
        n = 0
    logger = logger_list[n]
    return logger


##################################################################################################
# get list of devices and select one, using the serial number if there is more than 1
##################################################################################################

device_list = None
device = None
device_id = None
device_sn = None
raw_vars = None

def get_device(sn=None):
    global token, device_list, device, device_id, device_sn, firmware, battery, raw_vars, debug_setting
    if get_token() is None:
        return None
    if device is not None:
        if sn is None:
            return device
        if device_sn[:len(sn)].upper() == sn.upper():
            return device
    if debug_setting > 1:
        print(f"getting device")
    # get device list
    headers = {'token': token['value'], 'User-Agent': token['user_agent'], 'lang': token['lang'], 'Connection': 'keep-alive'}
    query = {'pageSize': 100, 'currentPage': 1, 'total': 0, 'queryDate': {'begin': 0, 'end':0} }
    response = requests.post(url="https://www.foxesscloud.com/c/v0/device/list", headers=headers, data=json.dumps(query))
    if response.status_code != 200:
        print(f"** get_device() got response code: {response.status_code}")
        return None
    result = response.json().get('result')
    if result is None:
        print(f"** no device list result data")
        return None
    total = result.get('total')
    if total is None or total == 0 or total > 100:
        print(f"** invalid list of devices returned: {total}")
        return None
    device_list = result.get('devices')
    # look for the device we want in the list
    n = None
    if len(device_list) == 1 and sn is None:
        n = 0
    else:
        for i in range(len(device_list)):
            if device_list[i]['deviceSN'][:len(sn)].upper() == sn.upper():
                n = i
                break
        if n is None:
            print(f"\nget_device(): please provide a serial number from this list:")
            for d in device_list:
                print(f"SN={d['deviceSN']}, Type={d['deviceType']}")
            return None
    # load information for the device
    device = device_list[n]
    device_id = device.get('deviceID')
    device_sn = device.get('deviceSN')
    firmware = None
    battery = None
    battery_settings = None
    raw_vars = get_vars()
    # parse the model code to work out attributes
    model_code = device['deviceType'].upper()
    # first 2 letters / numbers e.g. H1, H3, KH
    if model_code[:2] == 'KH':
        mode_code = 'KH-' + model_code[2:]
    elif model_code[:4] == 'AIO-':
        mode_code = 'AIO' + model_code[4:]
    device['eps'] = 'E' in model_code
    parts = model_code.split('-')
    model = parts[0]
    if model not in ['H1', 'H3', 'KH', 'AC1', 'AC3', 'AIOH1', 'AIOH3']:
        print(f"** device model not recognised for deviceType: {device['deviceType']}")
        return device
    device['model'] = model
    device['phase'] = 3 if model[-1:] == '3' else 1
    for p in parts[1:]:
        if p.replace('.','').isnumeric():
            power = float(p)
            if power >= 1.0 and power < 20.0:
                device['power'] = float(p)
            break
    if device.get('power') is None:
        print(f"** device power not found for deviceType: {device['deviceType']}")
    return device

##################################################################################################
# get list of raw_data variables for selected device
##################################################################################################

def get_vars():
    global token, device_id, debug_setting
    if get_device() is None:
        return None
    if debug_setting > 1:
        print(f"getting variables")
    headers = {'token': token['value'], 'User-Agent': token['user_agent'], 'lang': token['lang'], 'Connection': 'keep-alive'}
    params = {'deviceID': device_id}
    # v1 api required for full list with {name, variable, unit}
    response = requests.get(url="https://www.foxesscloud.com/c/v1/device/variables", params=params, headers=headers)
    if response.status_code != 200:
        print(f"** get_vars() got response code: {response.status_code}")
        return None
    result = response.json().get('result')
    if result is None:
        print(f"** no variables result")
        return None
    vars = result.get('variables')
    if vars is None:
        print(f"** no variables list")
        return None
    return vars

##################################################################################################
# get current firmware versions for selected device
##################################################################################################

firmware = None

def get_firmware():
    global token, device_id, firmware, debug_setting
    if get_device() is None:
        return None
    if debug_setting > 1:
        print(f"getting firmware")
    headers = {'token': token['value'], 'User-Agent': token['user_agent'], 'lang': token['lang'], 'Connection': 'keep-alive'}
    params = {'deviceID': device_id}
    response = requests.get(url="https://www.foxesscloud.com/c/v0/device/addressbook", params=params, headers=headers)
    if response.status_code != 200:
        print(f"** get_firmware() got response code: {response.status_code}")
        return None
    result = response.json().get('result')
    if result is None:
        print(f"** no firmware result data")
        return None
    firmware = result.get('softVersion')
    if firmware is None:
        print(f"** no firmware data")
        return None
    return firmware

##################################################################################################
# get battery info and save to battery
##################################################################################################

battery = None
battery_settings = None

def get_battery():
    global token, device_id, battery, debug_setting
    if get_device() is None:
        return None
    if debug_setting > 1:
        print(f"getting battery")
    headers = {'token': token['value'], 'User-Agent': token['user_agent'], 'lang': token['lang'], 'Connection': 'keep-alive'}
    params = {'id': device_id}
    response = requests.get(url="https://www.foxesscloud.com/c/v0/device/battery/info", params=params, headers=headers)
    if response.status_code != 200:
        print(f"** get_battery() got response code: {response.status_code}")
        return None
    result = response.json().get('result')
    if result is None:
        print(f"** no battery info")
        return None
    battery = result
    return battery

##################################################################################################
# get charge times and save to battery_settings
##################################################################################################

def get_charge():
    global token, device_sn, battery_settings, debug_setting
    if get_device() is None:
        return None
    if debug_setting > 1:
        print(f"getting charge times")
    headers = {'token': token['value'], 'User-Agent': token['user_agent'], 'lang': token['lang'], 'Connection': 'keep-alive'}
    params = {'sn': device_sn}
    response = requests.get(url="https://www.foxesscloud.com/c/v0/device/battery/time/get", params=params, headers=headers)
    if response.status_code != 200:
        print(f"** get_charge() got response code: {response.status_code}")
        return None
    result = response.json().get('result')
    if result is None:
        print(f"** no charge result data")
        return None
    times = result.get('times')
    if times is None:
        print(f"** no times data")
        return None
    if battery_settings is None:
        battery_settings = {}
    battery_settings['times'] = times
    return battery_settings


##################################################################################################
# set charge times from battery_settings or parameters
##################################################################################################

# helper to format time period structure
def time_period(t):
    result = f"{t['startTime']['hour']:02d}:{t['startTime']['minute']:02d} - {t['endTime']['hour']:02d}:{t['endTime']['minute']:02d}"
    if t['enableGrid']:
        result += f" Charge from grid"
    return result

def set_charge(ch1 = None, st1 = None, en1 = None, ch2 = None, st2 = None, en2 = None):
    global token, device_sn, battery_settings, debug_setting
    if get_device() is None:
        return None
    if battery_settings.get('times') is None or len(battery_settings['times']) != 2:
        print(f"** set_charge(): invalid battery settings")
        print(battery_settings)
        return None
    # configure time period 1
    if st1 is not None:
        if st1 == en1:
            st1 = 0
            en1 = 0
            ch1 = False
        st1 = time_hours(st1)
        en1 = time_hours(en1)
        battery_settings['times'][0]['enableCharge'] = True
        battery_settings['times'][0]['enableGrid'] = ch1
        battery_settings['times'][0]['startTime']['hour'] = int(st1)
        battery_settings['times'][0]['startTime']['minute'] = int(60 * (st1 - int(st1)))
        battery_settings['times'][0]['endTime']['hour'] = int(en1)
        battery_settings['times'][0]['endTime']['minute'] = int(60 * (en1 - int(en1)))
    # configure time period 2
    if st2 is not None:
        if st2 == en2:
            st2 = 0
            en2 = 0
            ch2 = False
        st2 = time_hours(st2)
        en2 = time_hours(en2)
        battery_settings['times'][1]['enableCharge'] = True
        battery_settings['times'][1]['enableGrid'] = ch2
        battery_settings['times'][1]['startTime']['hour'] = int(st2)
        battery_settings['times'][1]['startTime']['minute'] = int(60 * (st2 - int(st2)))
        battery_settings['times'][1]['endTime']['hour'] = int(en2)
        battery_settings['times'][1]['endTime']['minute'] = int(60 * (en2 - int(en2)))
    if debug_setting > 1:
        print(battery_settings)
        return None
    if debug_setting > 0:
        print(f"\nSetting time periods:")
        print(f"   Time Period 1 = {time_period(battery_settings['times'][0])}")
        print(f"   Time Period 2 = {time_period(battery_settings['times'][1])}")
    # set charge times
    headers = {'token': token['value'], 'User-Agent': token['user_agent'], 'lang': token['lang'], 'Connection': 'keep-alive'}
    data = {'sn': device_sn, 'times': battery_settings.get('times')}
    response = requests.post(url="https://www.foxesscloud.com/c/v0/device/battery/time/set", headers=headers, data=json.dumps(data))
    if response.status_code != 200:
        print(f"** set_charge() got response code: {response.status_code}")
        return None
    result = response.json().get('errno')
    if result != 0:
        print(f"** return code = {result}")
    elif debug_setting > 1:
        print(f"success") 
    return result

##################################################################################################
# get min soc settings and save in battery_settings
##################################################################################################

def get_min():
    global token, device_sn, battery_settings, debug_setting
    if get_device() is None:
        return None
    if debug_setting > 1:
        print(f"getting min soc")
    headers = {'token': token['value'], 'User-Agent': token['user_agent'], 'lang': token['lang'], 'Connection': 'keep-alive'}
    params = {'sn': device_sn}
    response = requests.get(url="https://www.foxesscloud.com/c/v0/device/battery/soc/get", params=params, headers=headers)
    if response.status_code != 200:
        print(f"** get_min() got response code: {response.status_code}")
        return None
    result = response.json().get('result')
    if result is None:
        print(f"** no min soc result data")
        return None
    if battery_settings is None:
        battery_settings = {}
    battery_settings['minSoc'] = result.get('minSoc')
    battery_settings['minGridSoc'] = result.get('minGridSoc')
    return battery_settings

##################################################################################################
# set min soc from battery_settings or parameters
##################################################################################################

def set_min(minGridSoc = None, minSoc = None):
    global token, device_sn, bat_settings, debug_setting
    if get_device() is None:
        return None
    if battery_settings.get('minGridSoc') is None or battery_settings.get('minSoc') is None:
        print(f"** no min soc settings")
        print(battery_settings)
        return None
    if minGridSoc is not None:
        battery_settings['minGridSoc'] = minGridSoc
    if minSoc is not None:
        battery_settings['minSoc'] = minSoc
    if debug_setting > 1:
        print(battery_settings)
        return None
    if debug_setting > 0:
        print(f"setting min soc")
    headers = {'token': token['value'], 'User-Agent': token['user_agent'], 'lang': token['lang'], 'Connection': 'keep-alive'}
    data = {'minGridSoc': battery_settings['minGridSoc'], 'minSoc': battery_settings['minSoc'], 'sn': device_sn}
    response = requests.post(url="https://www.foxesscloud.com/c/v0/device/battery/soc/set", headers=headers, data=json.dumps(data))
    if response.status_code != 200:
        print(f"** set_min() got response code: {response.status_code}")
        return None
    result = response.json().get('errno')
    if result != 0:
        print(f"** return code = {result}")
    elif debug_setting > 1:
        print(f"success") 
    return result

##################################################################################################
# get times and min soc settings and save in bat_settings
##################################################################################################

def get_settings():
    global battery_settings
    if battery_settings is None or battery_settings.get('times') is None:
        get_charge()
    if battery_settings.get('minGridSoc') is None:
        get_min()
    return battery_settings

##################################################################################################
# get work mode
##################################################################################################

work_mode = None

def get_work_mode():
    global token, device_id, work_mode, debug_setting
    if get_device() is None:
        return None
    if debug_setting > 1:
        print(f"getting work mode")
    headers = {'token': token['value'], 'User-Agent': token['user_agent'], 'lang': token['lang'], 'Connection': 'keep-alive'}
    params = {'id': device_id, 'hasVersionHead': 1, 'key': 'operation_mode__work_mode'}
    response = requests.get(url="https://www.foxesscloud.com/c/v0/device/setting/get", params=params, headers=headers)
    if response.status_code != 200:
        print(f"** get_work_mode() got response code: {response.status_code}")
        return None
    result = response.json().get('result')
    if result is None:
        print(f"** no work mode result data")
        return None
    values = result.get('values')
    if values is None:
        print(f"** no work mode values data")
        return None
    work_mode = values.get('operation_mode__work_mode')
    if work_mode is None:
        print(f"** no work mode data")
        return None
    return work_mode

##################################################################################################
# set work mode
##################################################################################################

work_modes = ['SelfUse', 'Feedin', 'Backup', 'PowerStation', 'PeakShaving']

def set_work_mode(mode):
    global token, device_id, work_modes, work_mode, debug_setting
    if get_device() is None:
        return None
    if mode not in work_modes:
        print(f"** work mode: must be one of {work_modes}")
        return None
    if debug_setting > 1:
        print(mode)
        return None
    if debug_setting > 0:
        print(f"setting work mode")
    headers = {'token': token['value'], 'User-Agent': token['user_agent'], 'lang': token['lang'], 'Connection': 'keep-alive'}
    data = {'id': device_id, 'key': 'operation_mode__work_mode', 'values': {'operation_mode__work_mode': mode}, 'raw': ''}
    response = requests.post(url="https://www.foxesscloud.com/c/v0/device/setting/set", headers=headers, data=json.dumps(data))
    if response.status_code != 200:
        print(f"** set_work_mode() got response code: {response.status_code}")
        return None
    result = response.json().get('errno')
    if result != 0:
        print(f"** return code = {result}")
        return None
    elif debug_setting > 1:
        print(f"success")
    work_mode = mode
    return work_mode


##################################################################################################
# get raw data values
# returns a list of variables and their values / attributes
# time_span = 'hour', 'day', 'week'. For 'week', gets history of 7 days up to and including d
# d = day 'YYYY-MM-DD'. Can also include 'HH:MM' in 'hour' mode
# v = list of variables to get
# summary = 0: raw data, 1: add max, min, sum, 2: summarise and drop raw data, 3: calculate state
##################################################################################################

# variables that cover inverter power data: generationPower must be first
power_vars = ['generationPower', 'feedinPower','loadsPower','gridConsumptionPower','batChargePower', 'batDischargePower', 'pvPower', 'meterPower2']
#  names after integration of power to energy. List must be in the same order as above. input_daily must be last
energy_vars = ['output_daily', 'feedin_daily', 'load_daily', 'grid_daily', 'bat_charge_daily', 'bat_discharge_daily', 'pv_energy_daily', 'ct2_daily', 'input_daily']

# option to flip CT2 - correct polarity is +ve for generation and -ve for load
flip_ct2 = False

def get_raw(time_span = 'hour', d = None, v = None, summary = 0):
    global token, device_id, debug_setting, raw_vars, off_peak1, off_peak2, peak, flip_ct2, tou_periods
    if get_device() is None:
        return None
    time_span = time_span.lower()
    if d is None:
        d = datetime.strftime(datetime.now(), "%Y-%m-%d %H:%M:%S" if time_span == 'hour' else "%Y-%m-%d")
    if time_span == 'week':
        result_list = []
        for d in date_list(e=d, span='week'):
            result = get_raw('day', d=d, v=v, summary=summary)
            if result is None:
                return None
            result_list += result
        return result_list
    if v is None:
        if raw_vars is None:
            raw_vars = get_vars()
        v = [x['variable'] for x in raw_vars]
    elif type(v) is not list:
        v = [v]
    if debug_setting > 1:
        print(f"getting raw data")
    headers = {'token': token['value'], 'User-Agent': token['user_agent'], 'lang': token['lang'], 'Connection': 'keep-alive'}
    query = {'deviceID': device_id, 'variables': v, 'timespan': time_span, 'beginDate': query_date(d)}
    response = requests.post(url="https://www.foxesscloud.com/c/v0/device/history/raw", headers=headers, data=json.dumps(query))
    if response.status_code != 200:
        print(f"** get_raw() got response code: {response.status_code}")
        return None
    result = response.json().get('result')
    if result is None:
        print(f"** no raw data")
        return None
    # integrate kW to kWh based on 5 minute samples
    if summary == 0:
        return result
    if debug_setting > 1:
        print(f"calculating summary data")
    # copy generationPower to produce inputPower data
    input_name = None
    if 'generationPower' in v:
        input_name = energy_vars[-1]
        input_result = deepcopy(result[v.index('generationPower')])
        input_result['name'] = input_name
        for y in input_result['data']:
            y['value'] = -y['value'] if y['value'] < 0.0 else 0.0
        result.append(input_result)
    # check if we need to flip CT2
    if flip_ct2 and 'meterPower2' in v:
        for x in result[v.index('meterPower2')]['data']:
            x['value'] = -x['value']
    for var in result:
        energy = var['unit'] == 'kW'
        hour = 0
        if energy:
            kwh = 0.0       # kwh total
            kwh_off = 0.0   # kwh during off peak time (02:00-05:00)
            kwh_peak = 0.0  # kwh during peak time (16:00-19:00)
        sum = 0.0
        count = 0
        max = None
        max_time = None
        min = None
        min_time = None
        if summary == 3 and energy:
            var['state'] = [{}]
        for y in var['data']:
            h = time_hours(y['time'][11:19]) # time
            value = y['value']
            sum += value
            count += 1
            max = value if max is None or value > max else max
            min = value if min is None or value < min else min
            if energy and value >= 0.0:
                e = value / 12        # convert 5 minute sample kW to kWh energy
                kwh += e
                if tou_periods is not None:
                    if h >= tou_periods['off_peak1']['start'] and h < tou_periods['off_peak1']['end']:
                        kwh_off += e
                    elif h >= tou_periods['off_peak2']['start'] and h < tou_periods['off_peak2']['end']:
                        kwh_off += e
                    elif h >= tou_periods['peak']['start'] and h < tou_periods['peak']['end']:
                        kwh_peak += e
                    elif h >= tou_periods['peak2']['start'] and h < tou_periods['peak2']['end']:
                        kwh_peak += e
            if summary == 3 and energy:
                if int(h) > hour:    # new hour
                    var['state'].append({})
                    hour += 1
                var['state'][hour]['time'] = y['time'][11:16]
                var['state'][hour]['state'] = round(kwh,3)
        if energy:
            var['kwh'] = round(kwh,3)
            var['kwh_off'] = round(kwh_off,3)
            var['kwh_peak'] = round(kwh_peak,3)
        var['date'] = d[0:10]
        var['count'] = count
        var['average'] = round(sum / count, 3) if count > 0 else None
        var['max'] = round(max, 3) if max is not None else None
        var['max_time'] = var['data'][[y['value'] for y in var['data']].index(max)]['time'][11:16] if max is not None else None
        var['min'] = round(min, 3) if min is not None else None
        var['min_time'] = var['data'][[y['value'] for y in var['data']].index(min)]['time'][11:16] if min is not None else None
        if summary >= 2:
            if energy and (input_name is None or var['name'] != input_name):
                var['name'] = energy_vars[power_vars.index(var['variable'])]
            if energy:
                var['unit'] = 'kWh'
            del var['data']
    return result

##################################################################################################
# get energy report data in kWh
##################################################################################################
# report_type = 'day', 'week', 'month', 'year'
# d = day 'YYYY-MM-DD'
# v = list of report variables to get
# totals = True, do a quick total energy report for a day

report_vars = ['generation', 'feedin', 'loads', 'gridConsumption', 'chargeEnergyToTal', 'dischargeEnergyToTal']

def get_report(report_type = 'day', d = None, v = None, totals = False ):
    global token, device_id, var_list, debug_setting, report_vars
    if get_device() is None:
        return None
    report_type = report_type.lower()
    if totals and report_type != 'day':
        totals = False
    headers = {'token': token['value'], 'User-Agent': token['user_agent'], 'lang': token['lang'], 'Connection': 'keep-alive'}
    if d is None:
        d = datetime.strftime(datetime.now() - timedelta(days=1), "%Y-%m-%d")
    if v is None:
        v = report_vars
    elif type(v) is not list:
        v = [v]
    if debug_setting > 1:
        print(f"getting report data")
    current_date = query_date(None)
    main_date = query_date(d)
    side_result = None
    if report_type in ('day', 'week'):
        # side report needed
        side_date = query_date(d, -7) if report_type == 'week' else main_date
        if report_type == 'day' or main_date['month'] != side_date['month']:
            query = {'deviceID': device_id, 'reportType': 'month', 'variables': v, 'queryDate': side_date}
            response = requests.post(url="https://www.foxesscloud.com/c/v0/device/history/report", headers=headers, data=json.dumps(query))
            if response.status_code != 200:
                print(f"** get_report() side report got response code: {response.status_code}")
                return None
            side_result = response.json().get('result')
            if side_result is None:
                print(f"** no side report data")
                return None
    if not totals:
        query = {'deviceID': device_id, 'reportType': report_type.replace('week', 'month'), 'variables': v, 'queryDate': main_date}
        response = requests.post(url="https://www.foxesscloud.com/c/v0/device/history/report", headers=headers, data=json.dumps(query))
        if response.status_code != 200:
            print(f"** get_report() main report got response code: {response.status_code}")
            return None
        result = response.json().get('result')
        if result is None:
            print(f"** no main report data")
            return None
        # prune results back to only valid, complete data for day, week, month or year
        if report_type == 'day' and main_date['year'] == current_date['year'] and main_date['month'] == current_date['month'] and main_date['day'] == current_date['day']:
            for var in result:
                # prune current day to hours that are valid
                var['data'] = var['data'][:int(current_date['hour'])]
        if report_type == 'week':
            for i, var in enumerate(result):
                # prune results to days required
                var['data'] = var['data'][:int(main_date['day'])]
                if side_result is not None:
                    # prepend side results (previous month) if required
                    var['data'] = side_result[i]['data'][int(side_date['day']):] + var['data']
                # prune to week required
                var['data'] = var['data'][-7:]
        elif report_type == 'month' and main_date['year'] == current_date['year'] and main_date['month'] == current_date['month']:
            for var in result:
                # prune current month to days that are valid
                var['data'] = var['data'][:int(current_date['day'])]
        elif report_type == 'year' and main_date['year'] == current_date['year']:
            for var in result:
                # prune current year to months that are valid
                var['data'] = var['data'][:int(current_date['month'])]
    else:
        # fake result for quick daily totals only
        result = []
        for x in v:
            result.append({'variable': x, 'data': []})
    # calculate and add summary data
    for i, var in enumerate(result):
        count = 0
        sum = 0.0
        max = None
        min = None
        for y in var['data']:
            value = y['value']
            count += 1
            sum += value
            max = value if max is None or value > max else max
            min = value if min is None or value < min else min
        # correct day total from side report
        var['total'] = round(sum,3) if report_type != 'day' else side_result[i]['data'][int(main_date['day'])-1]['value']
        if not totals:
            var['sum'] = round(sum,3)
            var['average'] = round(var['total'] / count, 3) if count > 0 else None
            var['date'] = d
            var['count'] = count
            var['max'] = round(max,3) if max is not None else None
            var['max_index'] = [y['value'] for y in var['data']].index(max) if max is not None else None
            var['min'] = round(min,3) if min is not None else None
            var['min_index'] = [y['value'] for y in var['data']].index(min) if min is not None else None
    return result


##################################################################################################
# get earnings data
##################################################################################################

def get_earnings():
    global token, device_id, var_list, debug_setting, report_vars
    if get_device() is None:
        return None
    if debug_setting > 1:
        print(f"getting earnings")
    headers = {'token': token['value'], 'User-Agent': token['user_agent'], 'lang': token['lang'], 'Connection': 'keep-alive'}
    params = {'deviceID': device_id}
    response = requests.get(url="https://www.foxesscloud.com/c/v0/device/earnings", params=params, headers=headers)
    if response.status_code != 200:
        print(f"** get_earnings() got response code: {response.status_code}")
        return None
    result = response.json().get('result')
    if result is None:
        print(f"** no earnings data")
        return None
    return result


##################################################################################################
##################################################################################################
# Operations section
##################################################################################################
##################################################################################################

##################################################################################################
# time of user (TOU)
# time values are decimal hours
##################################################################################################

# time periods for Octopus Flux
octopus_flux = {'name': 'Octopus Flux',
    'charge': {'start': 2.0, 'end': 5.0, 'force': 0},
    'off_peak1': {'start': 2.0, 'end': 5.0},
    'off_peak2': {'start': 0.0, 'end': 0.0},
    'peak': {'start': 16.0, 'end': 19.0 },
    'peak2': {'start': 0.0, 'end': 0.0 }}

# time periods for Intelligent Octopus
intelligent_octopus = {'name': 'Intelligent Octopus',
    'charge': {'start': 23.5, 'end': 5.5, 'force': 0},
    'off_peak1': {'start': 23.5, 'end': 24.0},
    'off_peak2': {'start': 0.0, 'end': 5.5},
    'peak': {'start': 0.0, 'end': 0.0 },
    'peak2': {'start': 0.0, 'end': 0.0 }}

# time periods for Octopus Cosy
octopus_cosy = {'name': 'Octopus Cosy',
    'charge': {'start': 4.0, 'end': 7.0, 'force': 0},
    'off_peak1': {'start': 4.0, 'end': 7.0},
    'off_peak2': {'start': 13.0, 'end': 16.0},
    'peak': {'start': 16.0, 'end': 19.0 },
    'peak2': {'start': 0.0, 'end': 0.0 }}

# time periods for Octopus Go
octopus_go = {'name': 'Octopus Go',
    'charge': {'start': 0.5, 'end': 4.5, 'force': 0},
    'off_peak1': {'start': 0.5, 'end': 4.5},
    'off_peak2': {'start': 0.0, 'end': 0.0},
    'peak': {'start': 0.0, 'end': 0.0 },
    'peak2': {'start': 0.0, 'end': 0.0 }}

# custom time periods / template
custom_periods = {'name': 'Custom',
    'charge': {'start': 2.0, 'end': 5.0, 'force': 0},
    'off_peak1': {'start': 0.0, 'end': 0.0},
    'off_peak2': {'start': 0.0, 'end': 0.0},
    'peak': {'start': 0.0, 'end': 0.0 },
    'peak2': {'start': 0.0, 'end': 0.0 }}

tariff_list = [octopus_flux, intelligent_octopus, octopus_cosy, octopus_go, custom_periods]

# global setting for tariff to use and charging
tou_periods = octopus_flux

# convert time string HH:MM:SS to decimal hours
def time_hours(s, d = None):
    if s is None:
        s = d
    if type(s) is float:
        return s
    elif type(s) is int:
        return float(s)
    elif type(s) is str and s.replace(':', '').isnumeric() and s.count(':') <= 2:
        s += ':00' if s.count(':') == 1 else ''
        return sum(float(t) / x for x, t in zip([1, 60, 3600], s.split(":")))
    print(f"** invalid time string for time_hours()")
    return None

# convert decimal hours to time string HH:MM:SS
def hours_time(h, ss = False):
    n = 8 if ss else 5
    return f"{int(h):02}:{int(h * 60 % 60):02}:{int(h * 3600 % 60):02}"[:n]


##################################################################################################
# calculate charge needed from current battery charge, forecast yield and expected load
##################################################################################################

# roll over 24 hours times and round times to 1 minute for time in decimal hours
def round_time(h):
    if h > 24:
        h -= 24
    return int(h) + round(60 * (h - int(h)), 0) / 60

# how consumption varies by month across a year. Total of all 12 values must be 12.0
seasonality = [1.1, 1.1, 1.0, 1.0, 0.9, 0.9, 0.9, 0.9, 1.0, 1.0, 1.1, 1.1]

# work out the charge times to set using the parameters:
#  forecast: the kWh expected tomorrow. If none, forecast data is loaded from solcast
#  annual_consumption: the kWh consumed each year via the inverter
#  contingency: a factor to add to allow for variations. 1.0 is no variation. Default is 1.25
#  start_at: time in hours when charging will start e.g. 1:30 = 1.5 hours
#  end_by: time in hours when charging will stop
#  force_charge: if True, the remainder of the time, force charge is set. If false, force charge is not set
#  charge_power: the kW of charge that will be applied
#  efficiency: inverter conversion factor from PV power or AC power to charge power. The default is 0.95 (95%)
#  run_after: the time in hours when calculation should take place. The default is 20 or 8pm.
#  update_settings: 1 allows inverter charge time settings to be updated. The default is 0

def charge_needed(forecast = None, annual_consumption = None, contingency = 1.25,
        start_at = None, end_by = None, force_charge = None,
        charge_power = None, efficiency = 0.92, run_after = 22, update_settings = 0):
    global device, seasonality, solcast_api_key, debug_setting, tou_periods
    print(f"\n---------- charge_needed ----------")
    # validate parameters
    args = locals()
    s = ''
    for k in [k for k in args.keys() if args[k] is not None]:
        s += f"\n   {k} = {args[k]}"
    if len(s) > 0:
        print(f"Parameters: {s}")
    now = datetime.now()
    if now.hour < run_after:
        print(f"Not time to run yet, time is {datetime.strftime(now, '%H:%M')}, run_after = {run_after}")
        return None
    tomorrow = datetime.strftime(now + timedelta(days=1), '%Y-%m-%d')
    start_at = time_hours(start_at, tou_periods['charge']['start'] if tou_periods is not None else 2.0)
    end_by = time_hours(end_by, tou_periods['charge']['end'] if tou_periods is not None else 5.0)
    if force_charge is None:
        force_charge = tou_periods['charge']['force'] if tou_periods is not None else None
        force_charge = 0 if force_charge is None else force_charge
    force_charge = 1 if force_charge == 1 or force_charge == True else 0
    update_settings = 1 if update_settings == 1 or update_settings == True else 0
    # get battery info
    get_settings()
    get_battery()
    min = battery_settings['minGridSoc']
    soc = battery['soc']
    residual = round(battery['residual']/1000, 1)
    capacity = round(residual * 100 / soc if soc > 0 else residual, 1)
    reserve = round(capacity * min / 100, 1)
    available = round(residual - reserve, 1)
    print(f"\nBattery:")
    print(f"   Capacity = {capacity}kWh")
    print(f"   Min SoC on Grid = {min}%")
    print(f"   Current SoC = {soc}%")
    print(f"   Residual = {residual}kWh")
    print(f"   Available = {available}kWh")
    # get forecast / history info
    expected = None
    forecast_values = None
    if forecast is not None:
        expected = round(forecast,1)
    elif solcast_api_key is not None and solcast_api_key != 'my.solcast_api_key':
        forecast = Solcast(quiet=True)
        if hasattr(forecast, 'daily'):
            forecast_values = [round(forecast.daily[k]['kwh'],1) for k in forecast.keys if forecast.daily[k]['forecast']][1:6]
            print(f"\nSolcast forecast for next 5 days:")
            print(f"   Solar: {forecast_values} kWh")
            print(f"   Average forecast: {round(sum(forecast_values)/5, 1)} kWh")
    history = get_raw('week', v=['pvPower','meterPower2'], summary=2)
    history_pv = [round(h['kwh'], 1) for h in history if h['variable'] == 'pvPower']
    sum_pv = sum(history_pv)
    history_ct2 = [round(h['kwh']/efficiency, 1) for h in history if h['variable'] == 'meterPower2']
    sum_ct2 = sum(history_ct2)
    print(f"\nGeneration over last 7 days:")
    print(f"   PV energy: {history_pv} kWh")
    if sum_ct2 > 0.0:
        print(f"  CT2 energy: {history_ct2} kWh")
    generation = round(sum_pv / 7 + sum_ct2 / 7, 1)
    print(f"   Average generation = {generation}kWh")
    # choose expected value
    if expected is not None:
        print(f"\nManual forecast for tomorrow = {expected}kWh")
    else:
        expected = forecast_values[0] if forecast_values is not None else generation
        print(f"\nForecast generation tomorrow = {expected}kWh")
    # get consumption info
    if annual_consumption is not None:
        consumption = round(annual_consumption / 365 * seasonality[now.month - 1], 1)
        if debug_setting > 0:
            print(f"\nEstimate of consumption = {consumption}kWh")
    else:
        history = get_report('week', v='loads')[0]['data']
        history_load = [round(h['value'], 1) for h in history]
        history_sum = sum(history_load)
        consumption = round(sum(history_load) / 7, 1)
        if debug_setting > 0:
            print(f"\nConsumption over last 7 days:")
            print(f"   Load: {history_load} kWh")
            print(f"   Average consumption = {consumption}kWh")
    # calculate charge to add to battery
    charge = round(consumption - available - expected / contingency, 1)
    print(f"\nComparing forecast, consumption and available energy:")
    if charge < 0.0:
        print(f"   => generation surplus = {-charge} kWh:")
        charge = 0.0
    else:
        print(f"   => charge needed = {charge}kWh:")
        if (residual + charge) > capacity:
            print(f"  ** charge needed exceeds battery capacity by {charge - capacity + residual}kWh")
    # calculate charge time
    if charge_power is None or charge_power <= 0:
        charge_power = device.get('power')
        if charge_power is None:
            charge_power = 3.7
    hours = round_time(charge / charge_power / efficiency)
    # don't charge for less than 15 minutes
    if hours > 0 and hours < 0.25:
        hours = 0.25
    if hours > 0:
        print(f"   => charge time needed is {hours} hours at {charge_power}kW charge power")
    else:
        print(f"   => no charging needed")
    # work out charge periods settings
    start1 = start_at
    end1 = round_time(start1 + hours)
    if end1 > end_by:
        print(f"** charge end time {hours_time(end1)} exceeds end by {hours_time(end_by)}")
        end1 = end_by
    if force_charge == 1:
        start2 = round_time(end1 + 1 / 60)
        start2 = end_by if start2 > end_by else start2
        end2 = end_by
    else:
        start2 = 0
        end2 = 0
    # setup charging
    if update_settings == 1:
        set_charge(ch1 = True, st1 = start1, en1 = end1, ch2 = False, st2 = start2, en2 = end2)
    else:
        print(f"\nNo changes have been made to your inverter settings")
    return None

##################################################################################################
# Date Ranges
##################################################################################################

# generate a list of dates, where the last date is not later than yesterday or today
# s and e: start and end dates using the format 'YYYY-MM-DD'
# limit: limits the total number of days (default is 200)
# today: 1 defaults the date to today as the last date, otherwise, yesterday
# span: 'week', 'month' or 'year' generated dates that span a week, month or year
# quiet: do not print results if True

def date_list(s = None, e = None, limit = None, span = None, today = 0, quiet = True):
    global debug_setting
    latest_date = datetime.date(datetime.now())
    today = 0 if today == False else 1 if today == True else today
    if today == 0:
        latest_date -= timedelta(days=1)
    first = datetime.date(datetime.strptime(s, '%Y-%m-%d')) if s is not None else None
    last = datetime.date(datetime.strptime(e, '%Y-%m-%d')) if e is not None else None
    if first is None and last is None:
        last = latest_date
    if span is not None:
        span = span.lower()
        limit = 366 if limit is None else limit
        if span == 'day':
            limit = 1
        elif span == '2days':
            # e.g. yesterday and today
            last = first + timedelta(days=1) if first is not None else last
            first = last - timedelta(days=1) if first is None else first
        elif span == 'week':
            # number of days in a week less 1 day
            last = first + timedelta(days=6) if first is not None else last
            first = last - timedelta(days=6) if first is None else first
        elif span == 'month':
            if first is not None:
                # number of days in this month less 1 day
                days = ((first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)).day - 1
            else:
                # number of days in previous month less 1 day
                days = (last.replace(day=1) - timedelta(days=1)).day - 1
            last = first + timedelta(days=days) if first is not None else last
            first = last - timedelta(days=days) if first is None else first
        elif span == 'year':
            if first is not None:
                # number of days in coming year
                days = (first.replace(year=first.year+1,day=28 if first.month==2 and first.day==29 else first.day) - first).days - 1
            else:
                # number of days in previous year
                days = (last - last.replace(year=last.year-1,day=28 if last.month==2 and last.day==29 else last.day)).days - 1
            last = first + timedelta(days=days) if first is not None else last
            first = last - timedelta(days=days) if first is None else first
        else:
            print(f"** span '{span}' was not recognised")
            return None
    else:
        limit = 200 if limit is None or limit < 1 else limit
    last = latest_date if last is None or last > latest_date else last
    d = latest_date if first is None or first > latest_date else first
    if d > last:
        d, last = last, d
    l = [datetime.strftime(d, '%Y-%m-%d')]
    while d < last  and len(l) < limit:
        d += timedelta(days=1)
        l.append(datetime.strftime(d, '%Y-%m-%d'))
    return l


##################################################################################################
##################################################################################################
# PV Output Section
##################################################################################################
##################################################################################################

##################################################################################################
# get PV Output upload data from the Fox Cloud as energy values for a list of dates
##################################################################################################

# get pvoutput data for upload to pvoutput api or via Bulk Loader
# tou: 0 = no time of use, 1 = use time of use periods if available

def get_pvoutput(d = None, tou = 0):
    if d is None:
        d = date_list()[0]
    tou = 0 if (tou == 1 or tou == True) and tou_periods is None else tou
    tou = 1 if tou == 1 or tou == True else 0
    if type(d) is list:
        print(f"\n---------- get_pvoutput ----------")
        print(f"Date range {d[0]} to {d[-1]} has {len(d)} days")
        if tou == 1:
            print(f"Time of use: {tou_periods['name']}\n")
        for x in d:
            csv = get_pvoutput(x)
            if csv is None:
                return None
            print(csv)
        return
    # get quick report of totals for the day
    v = ['loads'] if tou else ['loads', 'feedin', 'gridConsumption']
    report_data = [] if tou else get_report('day', d=d, v = v, totals = True)
    if report_data is None:
        return None
    # get raw power data for the day
    v = ['pvPower', 'meterPower2'] + (['feedinPower', 'gridConsumptionPower'] if tou else [])
    raw_data = get_raw('day', d=d + ' 00:00:00', v=v , summary=1)
    if raw_data is None:
        return None
    # merge raw_data for meterPower2 into pvPower:
    pv_index = v.index('pvPower')
    ct2_index = v.index('meterPower2')
    for i, data in enumerate(raw_data[ct2_index]['data']):
        raw_data[pv_index]['data'][i]['value'] += data['value'] / 0.92 if data['value'] > 0.0 else 0
    raw_data[pv_index]['kwh'] += raw_data[ct2_index]['kwh']
    pv_max = max(data['value'] for data in raw_data[pv_index]['data'])
    max_index = [data['value'] for data in raw_data[pv_index]['data']].index(pv_max)
    raw_data[pv_index]['max'] = pv_max
    raw_data[pv_index]['max_time'] = raw_data[pv_index]['data'][max_index]['time'][11:16]
    # generate output
    generate = ''
    export = ','
    power = ',,'
    export_tou = ',,,'
    consume = ','
    grid = ',,,,'
    for var in raw_data:     # process list of raw_data values (with TOU)
        wh = int(var['kwh'] * 1000)
        peak = int(var['kwh_peak'] * 1000)
        off_peak = int(var['kwh_off'] * 1000)
        if var['variable'] == 'pvPower':
            generate = f"{var['date'].replace('-','')},{wh},"
            power = f"{int(var['max'] * 1000)},{var['max_time']},"
        elif var['variable'] == 'feedinPower':
            export = f"{wh}," if tou == 0 else f","
            export_tou = f",,," if tou == 0 else f"{peak},{off_peak},{wh - peak - off_peak},0"
        elif var['variable'] == 'loadsPower':
            consume = f"{wh},"
        elif var['variable'] == 'gridConsumptionPower':
            grid = f"0,0,{wh},0," if tou == 0 else f"{peak},{off_peak},{wh - peak - off_peak},0,"
    for var in report_data:     # process list of report_data values (no TOU)
        wh = int(var['total'] * 1000)
        if var['variable'] == 'feedin':
            export = f"{wh},"
            export_tou = f",,,"
        elif var['variable'] == 'loads':
            consume = f"{wh},"
        elif var['variable'] == 'gridConsumption':
            grid = f"0,0,{wh},0,"
    if generate == '':
        return None
    csv = generate + export + power + ',,,,' + grid + consume + export_tou
    return csv

pv_url = "https://pvoutput.org/service/r2/addoutput.jsp"
pv_api_key = None
pv_system_id = None

# upload data for a day using pvoutput api
def set_pvoutput(d = None, tou = 0):
    global pv_url, pv_api_key, pv_system_id
    if pv_api_key is None or pv_system_id is None or pv_api_key == 'my.pv_api_key' or pv_system_id == 'my.pv_system_id':
        print(f"** set_pvoutput: pv_api_key / pv_system_id not set")
        return None
    if d is None:
        d = date_list(span='2days', today = 1)
    tou = 0 if (tou == 1 or tou == True) and tou_periods is None else tou
    tou = 1 if tou == 1 or tou == True else 0
    if type(d) is list:
        print(f"\n---------- set_pvoutput ----------")
        print(f"Date range {d[0]} to {d[-1]} has {len(d)} days\n")
        if tou == 1 :
            print(f"Time of use: {tou_periods['name']}\n")
        for x in d[:10]:
            csv = set_pvoutput(x)
            if csv is None:
                return None
            print(f"{csv}  # uploaded OK")
        return
    headers = {'X-Pvoutput-Apikey': pv_api_key, 'X-Pvoutput-SystemId': pv_system_id, 'Content-Type': 'application/x-www-form-urlencoded'}
    csv = get_pvoutput(d, tou)
    if csv is None:
        return None
    response = requests.post(url=pv_url, headers=headers, data='data=' + csv)
    result = response.status_code
    if result != 200:
        print(f"** set_pvoutput got response code: {result}")
        return None
    return csv


##################################################################################################
##################################################################################################
# Solcast Section
##################################################################################################
##################################################################################################

def c_int(i):
    # handle None in integer conversion
    if i is None :
        return None
    return int(i)

def c_float(n):
    # handle None in float conversion
    if n is None :
        return float(0)
    return float(n)

##################################################################################################
# Code for loading and displaying yield forecasts from Solcast.com.au.
##################################################################################################

# solcast settings
solcast_url = 'https://api.solcast.com.au/'
solcast_api_key = None
solcast_rids = []
solcast_save = 'solcast.json'
solcast_cal = 1.0
page_width = 100        # maximum text string for display
figure_width = 24       # width of plots

class Solcast :
    """
    Load Solcast Estimate / Actuals / Forecast daily yield
    """ 

    def __init__(self, days = 7, reload = 2, quiet = False) :
        # days sets the number of days to get for forecasts and estimated
        # reload: 0 = use solcast.json, 1 = load new forecast, 2 = use solcast.json if date matches
        # The forecasts and estimated both include the current date, so the total number of days covered is 2 * days - 1.
        # The forecasts and estimated also both include the current time, so the data has to be de-duplicated to get an accurate total for a day
        global debug_setting, solcast_url, solcast_api_key, solcast_rids, solcast_save, solcast_cal
        data_sets = ['forecasts', 'estimated_actuals']
        self.data = {}
        self.today =datetime.strftime(datetime.date(datetime.now()), '%Y-%m-%d')
        if reload == 1 and os.path.exists(solcast_save):
            os.remove(solcast_save)
        if solcast_save is not None and os.path.exists(solcast_save):
            f = open(solcast_save)
            self.data = json.load(f)
            f.close()
            if len(self.data) == 0:
                print(f"No data in {solcast_save}")
            elif reload == 2 and 'date' in self.data and self.data['date'] != self.today:
                self.data = {}
            elif debug_setting > 0 and not quiet:
                print(f"Using forecast for {self.data['date']} from {solcast_save}")
        if len(self.data) == 0 :
            if solcast_api_key is None or solcast_api_key == 'my.solcast_api_key>':
                print(f"\nSolcast: solcast_api_key not set, exiting")
                return
            if solcast_rids is None or type(solcast_rids) != list or len(solcast_rids) < 1:
                print(f"\nSolcast: solcast_rids not set, exiting")
                return
            if debug_setting > 0 and not quiet:
                print(f"Getting forecast for {self.today} from solcast.com")
            self.credentials = HTTPBasicAuth(solcast_api_key, '')
            self.data['date'] = self.today
            params = {'format' : 'json', 'hours' : 168, 'period' : 'PT30M'}     # always get 168 x 30 min values
            for t in data_sets :
                self.data[t] = {}
                for rid in solcast_rids :
                    response = requests.get(solcast_url + 'rooftop_sites/' + rid + '/' + t, auth = self.credentials, params = params)
                    if response.status_code != 200 :
                        if response.status_code == 429:
                            print(f"\nSolcast API call limit reached for today")
                        else:
                            print(f"Solcast: response code getting {t} was {response.status_code}")
                        return
                    self.data[t][rid] = response.json().get(t)
            if solcast_save is not None :
                f = open(solcast_save, 'w')
                json.dump(self.data, f, sort_keys = True, indent=4, ensure_ascii= False)
                f.close()
        self.daily = {}
        self.rids = []
        for t in data_sets :
            for rid in self.data[t].keys() :            # aggregate sites
                if self.data[t][rid] is not None :
                    self.rids.append(rid)
                    for f in self.data[t][rid] :            # aggregate 30 minute slots for each day
                        period_end = f.get('period_end')
                        date = period_end[:10]
                        time = period_end[11:16]
                        if date not in self.daily.keys() :
                            self.daily[date] = {'forecast' : t == 'forecasts', 'kwh' : 0.0}
                        if rid not in self.daily[date].keys() :
                            self.daily[date][rid] = []
                        if time not in self.daily[date][rid] :
                            self.daily[date]['kwh'] += c_float(f.get('pv_estimate')) / 2      # 30 minute kw yield / 2 = kwh
                            self.daily[date][rid].append(time)
                        elif debug_setting > 1 :
                                print(f"Solcast: overlapping data was ignored for {rid} in {t} at {date} {time}")
        # ignore first and last dates as these forecast and estimate only cover part of the day, so are not accurate
        self.keys = sorted(self.daily.keys())[1:-1]
        self.days = len(self.keys)
        # trim the range if fewer days have been requested
        while self.days > 2 * days :
            self.keys = self.keys[1:-1]
            self.days = len(self.keys)
        self.values = [self.daily[k]['kwh'] for k in self.keys]
        self.total = sum(self.values)
        if self.days > 0 :
            self.avg = self.total / self.days
        self.cal = solcast_cal
        return

    def __str__(self) :
        # return printable Solcast info
        global debug_setting
        s = f'\nSolcast yield for {self.days} days'
        if self.cal is not None and self.cal != 1.0 :
            s += f", calibration = {self.cal}"
        s += f" (E = estimated, F = forecasts):\n\n"
        for k in self.keys :
            tag = 'F' if self.daily[k]['forecast'] else 'E'
            y = self.daily[k]['kwh'] * self.cal
            d = datetime.strptime(k, '%Y-%m-%d').strftime('%A')[:3]
            s += "\033[1m--> " if k == self.today else "    "
            s += f"{k} {d} {tag}: {y:5.2f} kwh"
            s += "\033[0m\n" if k == self.today else "\n"
            for r in self.rids :
                n = len(self.daily[k][r])
                if n != 48 and debug_setting > 0:
                    print(f"Solcast: {k} rid {r} should have 48 x 30 min values. {n} values found")
        return s

    def plot_daily(self) :
        if not hasattr(self, 'daily') :
            print(f"Solcast: ** no daily data available")
            return
        figwidth = 12 * self.days / 7
        self.figsize = (figwidth, figwidth/3)     # size of charts
        plt.figure(figsize=self.figsize)
        # plot estimated
        x = [f"{k} {datetime.strptime(k, '%Y-%m-%d').strftime('%A')[:3]} " for k in self.keys if not self.daily[k]['forecast']]
        y = [self.daily[k]['kwh'] * self.cal for k in self.keys if not self.daily[k]['forecast']]
        if x is not None and len(x) != 0 :
            plt.bar(x, y, color='orange', linestyle='solid', label='estimated', linewidth=2)
        # plot forecasts
        x = [f"{k} {datetime.strptime(k, '%Y-%m-%d').strftime('%A')[:3]} " for k in self.keys if self.daily[k]['forecast']]
        y = [self.daily[k]['kwh'] * self.cal for k in self.keys if self.daily[k]['forecast']]
        if x is not None and len(x) != 0 :
            plt.bar(x, y, color='green', linestyle='solid', label='forecast', linewidth=2)
        # annotations
        if hasattr(self, 'avg') :
            plt.axhline(self.avg, color='blue', linestyle='solid', label=f'average {self.avg:.1f} kwh / day', linewidth=2)
        title = f"Solcast yield on {self.today} for {self.days} days"
        if self.cal != 1.0 :
            title += f" (calibration = {self.cal})"
        title += f". Total yield = {self.total:.0f} kwh"    
        plt.title(title, fontsize=16)
        plt.grid()
        plt.legend(fontsize=14)
        plt.xticks(rotation=45, ha='right')
        plt.show()
        return
