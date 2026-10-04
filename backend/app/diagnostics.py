def exception_location(error: BaseException) -> str:
    """Return the failure site without formatting exception text or local values."""
    trace = error.__traceback__
    if trace is None:
        return "unknown"
    while trace.tb_next is not None:
        trace = trace.tb_next
    code = trace.tb_frame.f_code
    return f"{code.co_filename}:{trace.tb_lineno} in {code.co_name}"
