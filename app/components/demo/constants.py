from uuid import UUID, uuid5

DEMO_USER_ID = UUID("254477df-1d64-5d68-900f-dcbb4400de12")
DEMO_EMAIL = "demo@archy.example"


def sample_id(name):
    return uuid5(DEMO_USER_ID, name)
