# pyright: reportInvalidTypeForm=false
# pyright: reportMissingImports=false
"""Validierungs-Funktionen für Unity Tools Addon."""

import os
from .exceptions import ValidationError


def validate_unity_project(path: str) -> bool:
	"""
	Validiert Unity-Projektpfad.
	
	Prüft auf das Vorhandensein von:
	- Assets/ Verzeichnis
	- ProjectSettings/ Verzeichnis
	
	Args:
		path: Zu validierender Projektpfad
	
	Returns:
		True wenn gültiges Unity-Projekt
	
	Raises:
		ValidationError: Wenn Pfad ungültig oder keine Unity-Struktur
	"""
	if not path:
		raise ValidationError("Projektpfad ist leer")
	
	if not os.path.exists(path):
		raise ValidationError(f"Pfad existiert nicht: {path}")
	
	if not os.path.isdir(path):
		raise ValidationError(f"Pfad ist kein Verzeichnis: {path}")
	
	# Unity-Struktur prüfen
	assets_path = os.path.join(path, "Assets")
	settings_path = os.path.join(path, "ProjectSettings")
	
	if not os.path.isdir(assets_path):
		raise ValidationError(f"Assets-Ordner nicht gefunden in: {path}")
	
	if not os.path.isdir(settings_path):
		raise ValidationError(f"ProjectSettings-Ordner nicht gefunden in: {path}")
	
	return True


def validate_godot_project(path: str) -> bool:
	"""
	Validiert Godot-Projektpfad.
	
	Prüft auf das Vorhandensein von:
	- project.godot Datei
	
	Args:
		path: Zu validierender Projektpfad
	
	Returns:
		True wenn gültiges Godot-Projekt
	
	Raises:
		ValidationError: Wenn Pfad ungültig oder keine Godot-Struktur
	"""
	if not path:
		raise ValidationError("Projektpfad ist leer")
	
	if not os.path.exists(path):
		raise ValidationError(f"Pfad existiert nicht: {path}")
	
	project_file = os.path.join(path, "project.godot")
	if not os.path.isfile(project_file):
		raise ValidationError(f"project.godot nicht gefunden in: {path}")
	
	return True


def detect_engine(path: str) -> str:
	"""
	Erkennt welche Game-Engine das Projekt verwendet.
	
	Args:
		path: Projektpfad
	
	Returns:
		'UNITY' oder 'GODOT'
	
	Raises:
		ValidationError: Wenn keine Engine erkannt wurde
	"""
	try:
		validate_unity_project(path)
		return 'UNITY'
	except ValidationError:
		pass
	
	try:
		validate_godot_project(path)
		return 'GODOT'
	except ValidationError:
		pass
	
	raise ValidationError(f"Pfad ist weder Unity- noch Godot-Projekt: {path}")


def validate_material(material) -> bool:
	"""
	Validiert dass ein Material exportiert werden kann.
	
	Prüft auf:
	- Material existiert
	- Node-Setup ist aktiv
	- Output-Node vorhanden und verbunden
	
	Args:
		material: Blender Material-Objekt
	
	Returns:
		True wenn Material gültig
	
	Raises:
		ValidationError: Wenn Material ungültig
	"""
	if not material:
		raise ValidationError("Material ist None")
	
	if not material.use_nodes:
		raise ValidationError(f"Material '{material.name}' verwendet keine Nodes")
	
	if not material.node_tree or not material.node_tree.nodes:
		raise ValidationError(f"Material '{material.name}' hat keinen Node-Tree")
	
	# Output-Node prüfen
	output_node = next(
		(n for n in material.node_tree.nodes if n.type == 'OUTPUT_MATERIAL'), 
		None
	)
	
	if not output_node:
		raise ValidationError(f"Material '{material.name}' hat keinen Output-Node")
	
	if not output_node.inputs['Surface'].links:
		raise ValidationError(f"Material '{material.name}' Output ist nicht verbunden")
	
	return True

