"""This module contains the definition of validation errors and warnings raised during graph methods
"""

from cognite.neat.constants import DEFAULT_DOCS_URL
from cognite.neat.exceptions import NeatException

DOCS_BASE_URL = f"{DEFAULT_DOCS_URL}api/exceptions.html#{__name__}"


class UnsupportedPropertyType(NeatException):
    """Unsupported property type when processing the graph capturing sheet

    Args:
        property_type: property type that is not supported
        verbose: flag that indicates whether to provide enhanced exception message, by default False
    """

    type_: str = "UnsupportedPropertyType"
    code: int = 1000
    description: str = "Unsupported property type when processing the graph capturing sheet."
    example: str = ""
    fix: str = ""

    def __init__(self, property_type: str, verbose: bool = False):
        self.property_type = property_type

        self.message = (
            f"Property type {self.property_type} is not supported. "
            " Only the following property types are supported: DatatypeProperty and ObjectProperty"
            f"\nFor more information visit: {DOCS_BASE_URL}.{self.__class__.__name__}"
        )

        if verbose:
            self.message += f"\nDescription: {self.description}"
            self.message += f"\nExample: {self.example}"
            self.message += f"\nFix: {self.fix}"
        super().__init__(self.message)
