def calculate_pi_spigot(digits):
    """
    Calculates digits of Pi using a spigot algorithm.
    This version corrects the carry propagation logic.
    """
    pi_digits = []
    # We calculate one extra digit for the leading '3'.
    num_iterations = digits + 1
    # The required array size is floor(10 * n / 3) + 1
    array_size = int(10 * num_iterations / 3) + 1
    a = [2] * array_size
    n = array_size

    # Loop for each digit to be generated
    for _ in range(num_iterations):
        # Multiply each element in the array by 10
        for i in range(n):
            a[i] *= 10
        
        # Normalize the array by carrying values from right to left.
        for i in range(n - 1, 0, -1):
            denominator = 2 * i + 1
            if denominator == 0: continue
            q = a[i] // denominator
            r = a[i] % denominator
            a[i] = r
            # This is the critical fix: The carry must be multiplied by the position 'i'.
            a[i-1] += q * i

        # Extract the next digit from the first element.
        digit = a[0] // 10
        remainder = a[0] % 10
        a[0] = remainder
        
        pi_digits.append(str(digit))
        
    # This algorithm can produce digits > 9 (like 10), which requires a carry-over step.
    # For this implementation, we will perform a simple post-processing carry operation.
    for i in range(len(pi_digits) - 1, 0, -1):
        d = int(pi_digits[i])
        if d > 9:
            pi_digits[i] = str(d % 10)
            pi_digits[i-1] = str(int(pi_digits[i-1]) + d // 10)

    # Format the list of digits into the final string with a decimal point.
    result = pi_digits[0] + "." + "".join(pi_digits[1:digits+1])
    return result

# Script execution starts here
num_digits = 100
pi_value = calculate_pi_spigot(num_digits)
print(f"Pi calculated to {num_digits} decimal places:")
print(pi_value)