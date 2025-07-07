def is_prime(n):
    if n <= 1:
        return False
    for i in range(2, int(n**0.5) + 1):
        if n % i == 0:
            return False
    return True

prime_sum = 0
for number in range(1, 101):
    if is_prime(number):
        prime_sum += number

print(prime_sum)