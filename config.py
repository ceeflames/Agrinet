# ===== AgriNet Configuration =====
# Change these values anytime without touching other code

# Paystack API Keys - Replace with your actual keys from paystack.com/dashboard
PAYSTACK_SECRET_KEY = "sk_test_70e3447a140287e0a93c5ced02abb4b0cd09b26d"
PAYSTACK_PUBLIC_KEY = "pk_test_06768a9a55ad4b6ac1d8136ef7323c3b416b179a"

# Commission Rates (as decimals)
COMMISSION_RATES = {
    "produce": 0.07,      # 7% on produce sales
    "investment": 0.04,   # 4% on investments
    "cold_room": 0.05,    # 5% on cold room bookings
    "vet": 0.10,          # 10% on vet consultation fees
}

# Minimum withdrawal amount in Naira
MIN_WITHDRAWAL = 1000

# Platform name
PLATFORM_NAME = "AgriNet"
PLATFORM_EMAIL = "payments@agrinet.com"

# Callback URL - update this when you deploy to Back4app
PAYSTACK_CALLBACK_URL = "http://localhost:8020/payments/callback"