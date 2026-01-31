import random
import time

otp_storage = {}

def generate_otp():
    return "".join([str(random.randint(0, 9)) for _ in range(6)])

def get_otp(user_email):
    otp = generate_otp()
    expiration = time.time() + 300

    otp_storage[user_email] = {"otp": otp, "expiration": expiration}
    return otp

def verify_otp(otp, user_email):
    try:
        if user_email in otp_storage and otp == otp_storage[user_email]["otp"]:
            if time.time() < otp_storage[user_email]["expiration"]:
                del otp_storage[user_email]
                return True
    except Exception as e:
        print(e)
    return False