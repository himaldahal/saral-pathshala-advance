import string
import random

def generate_random_slug(length:int=6):
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(length))