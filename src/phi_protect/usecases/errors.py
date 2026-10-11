class UnverifiableFileError(Exception):
    """The file cannot be fully checked for PHI, so it must be treated as unsafe.

    The message is shown to users; it must never contain file content.
    """
