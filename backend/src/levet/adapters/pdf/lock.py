import threading

# PyMuPDF must not be used from several threads at once. The background worker
# and web requests both reach it, so every use takes this lock.
PDF_LOCK = threading.RLock()
