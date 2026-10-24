def calc_fibonacci(n: int) -> int:
    """
    Calculate the Nth Fibonacci number using Fast Doubling (O(log n)).
    
    Args:
        n (int): The position in the Fibonacci sequence (0-based).
                 Must be a non-negative integer.
    
    Returns:
        int: The Nth Fibonacci number.
    
    Raises:
        ValueError: If n is negative.
    """
    if n < 0:
        raise ValueError("n must be non-negative")
    if n == 0: return 0
    
    def _fib(n):
        if n == 0: return (0, 1)
        else:
            a, b = _fib(n // 2)
            c = a * (b * 2 - a)
            d = a * a + b * b
            if n % 2 == 0: return (c, d)
            else: return (d, c + d)
            
    return _fib(n)[0]
