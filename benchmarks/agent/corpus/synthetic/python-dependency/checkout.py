from payment import process_payment


def checkout() -> bool:
    return process_payment()
