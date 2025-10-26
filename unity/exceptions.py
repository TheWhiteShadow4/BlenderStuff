# pyright: reportInvalidTypeForm=false
# pyright: reportMissingImports=false
"""Custom Exceptions für Unity Tools Addon."""


class AddonError(Exception):
	"""Basis-Exception für Unity Tools Addon."""
	pass


class ValidationError(AddonError):
	"""Wird geworfen wenn Validierung fehlschlägt (Projekt, Material, Bake-Daten)."""
	pass


class ExportError(AddonError):
	"""Wird geworfen wenn Export fehlschlägt (FBX, Material, Textur)."""
	pass

