"""What the Outlook route actually exposes — D-08, §3.1a.

`doctor` reported the route as ready when `win32com.client` imported.
That says a Python package is installed. It does not say Outlook is
reachable, that it is the classic build with a COM interface at all, or
that the mailbox Control is scoped to is in the profile — three
different failures with three different fixes, all of which looked
identical.
"""

from control.outlook import available_mailboxes


class Store:
    def __init__(self, smtp="", name=""):
        if smtp:
            self.SmtpAddress = smtp
        self.Name = name


class Namespace:
    def __init__(self, stores):
        self.Folders = stores


def test_the_profiles_mailboxes_are_named():
    found, problem = available_mailboxes(Namespace([
        Store(smtp="Control@ubcsis.com"), Store(smtp="ahmed@ubcsis.com")]))
    assert problem == ""
    assert found == ["control@ubcsis.com", "ahmed@ubcsis.com"]


def test_a_store_with_no_address_is_still_reported():
    """A PST or a shared folder with no SMTP address is still something
    the profile exposes. Dropping it would understate what this route
    can reach, which is D-08's objection to it."""
    found, _ = available_mailboxes(Namespace([Store(name="Archive 2021")]))
    assert found == ["Archive 2021 (no SMTP address on the store)"]


def test_an_empty_profile_is_reported_as_empty_not_as_working():
    found, problem = available_mailboxes(Namespace([]))
    assert found == [] and problem == ""


def test_a_profile_that_cannot_be_read_says_why():
    class Broken:
        @property
        def Folders(self):
            raise OSError("MAPI not initialised")

    found, problem = available_mailboxes(Broken())
    assert found == []
    assert "profile could not be read" in problem
