"""Library exceptions. Only the outer CLI chooses exit codes."""
class FastMossError(Exception):
    pass
class BrowserSkillError(FastMossError):
    pass
class BrowserNotConnectedError(BrowserSkillError):
    pass
class FastMossLoginError(FastMossError):
    pass
class FilterNotFoundError(FastMossError):
    pass
class FilterVerificationError(FastMossError):
    pass
class CategoryDiscoveryError(FastMossError):
    pass
class NoDataError(FastMossError):
    pass
class ParseError(FastMossError):
    pass

class CLIUsageError(FastMossError):
    pass
