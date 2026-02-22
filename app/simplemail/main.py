from iafisher_foundation.prelude import *
from lib import command, simplemail


def main(*, subject: str, body: str, recipient: List[str]) -> None:
    simplemail.send_email(subject, body, recipients=recipient, html=False)


cmd = command.Command.from_function(main, help="Send an email.")

if __name__ == "__main__":
    command.dispatch(cmd)
