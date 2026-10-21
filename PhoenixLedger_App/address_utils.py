"""Postal formatting that preserves existing unsplit addresses."""

def customer_address(address='',city='',state='',zip_code=''):
    street=str(address or '').strip()
    city=str(city or '').strip()
    state=str(state or '').strip()
    zip_code=str(zip_code or '').strip()
    local=', '.join(x for x in (city,state) if x)
    local=' '.join(x for x in (local,zip_code) if x)
    return '\n'.join(x for x in (street,local) if x)
