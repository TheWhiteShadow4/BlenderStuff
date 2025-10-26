# pyright: reportInvalidTypeForm=false
# pyright: reportMissingImports=false
"""
Hair Particle Converter
Konvertiert Hair-Partikel-Systeme in Mesh-Kurven mit korrektem Profil
"""

import bpy
import mathutils

class HairParticleConverter:
    """Konvertiert Hair-Partikel zu Kurven mit Profil"""
    
    def __init__(self, report_callback=None):
        """
        Args:
            report_callback: Optional callback für Statusmeldungen (z.B. operator.report)
        """
        self.report = report_callback
    
    def _log(self, level, message):
        """Logging-Hilfsfunktion"""
        if self.report:
            self.report({level}, message)
    
    def _get_hair_shape_data(self, obj, particle_system):
        """
        Extrahiert Hair Shape Daten vor der Konvertierung
        
        Returns:
            dict: {
                'root_radius': float,
                'tip_radius': float,
                'radius_scale': float,
                'shape': float  # -1.0 bis 1.0 (spitz bis stumpf)
            }
        """
        settings = particle_system.settings
        
        # Hair Shape Daten aus den Particle Settings
        shape_data = {
            'root_radius': settings.root_radius if hasattr(settings, 'root_radius') else 1.0,
            'tip_radius': settings.tip_radius if hasattr(settings, 'tip_radius') else 0.0,
            'radius_scale': settings.radius_scale if hasattr(settings, 'radius_scale') else 0.01,
            'shape': settings.shape if hasattr(settings, 'shape') else 0.0,
        }
        
        return shape_data
    
    def _get_hair_material(self, obj, particle_system):
        """
        Ermittelt das Material für das Hair-Partikel-System
        
        Args:
            obj: Das Original-Objekt
            particle_system: Das Partikel-System
            
        Returns:
            bpy.types.Material oder None
        """
        settings = particle_system.settings
        
        # Prüfen ob das Objekt überhaupt Material-Slots hat
        if not obj.material_slots or len(obj.material_slots) == 0:
            return None
        
        # Material aus den Particle Settings holen
        material_slot = settings.material_slot if hasattr(settings, 'material_slot') else 1
        
        # Variante 1: material_slot ist ein Material-Name (String)
        if isinstance(material_slot, str):
            # Nach Material-Slot mit diesem Namen suchen
            for slot in obj.material_slots:
                if slot.material and slot.material.name == material_slot:
                    return slot.material
            # Nicht gefunden? Fallback auf erstes Material
            return obj.material_slots[0].material if obj.material_slots[0] else None
        
        # Variante 2: material_slot ist ein Index (Integer, 1-basiert)
        try:
            slot_index = int(material_slot) - 1  # 1-basiert → 0-basiert
            
            # Sicherstellen dass der Index gültig ist
            if slot_index < 0 or slot_index >= len(obj.material_slots):
                # Fallback auf erstes Material
                slot_index = 0
            
            material_slot_obj = obj.material_slots[slot_index]
            return material_slot_obj.material if material_slot_obj else None
        except (ValueError, TypeError):
            # Fallback auf erstes Material
            return obj.material_slots[0].material if obj.material_slots[0] else None
    
    def _apply_material_to_curve(self, curve_obj, material):
        """
        Weist einem Kurven-Objekt ein Material zu
        
        Args:
            curve_obj: Das Kurven-Objekt
            material: Das zuzuweisende Material
        """
        if not curve_obj or not material:
            return
        
        # Alle bestehenden Material-Slots entfernen
        curve_obj.data.materials.clear()
        
        # Material hinzufügen
        curve_obj.data.materials.append(material)
        
        self._log('INFO', f"Material '{material.name}' zu Kurve '{curve_obj.name}' zugewiesen")
    
    def _calculate_bevel_resolution(self, particle_count):
        """
        Berechnet die Bevel Resolution basierend auf Partikelanzahl
        
        Args:
            particle_count: Anzahl der Partikel
            
        Returns:
            int: Resolution (0, 1, oder 2)
        """
        if particle_count > 1000:
            return 0
        elif particle_count > 100:
            return 1
        else:
            return 2
    
    def _apply_hair_profile_to_curve(self, curve_obj, shape_data, particle_count):
        """
        Wendet das Hair-Profil auf ein Kurven-Objekt an
        
        Args:
            curve_obj: Das Kurven-Objekt
            shape_data: Die Hair Shape Daten
            particle_count: Anzahl der ursprünglichen Partikel
        """
        if not curve_obj or curve_obj.type != 'CURVE':
            return
        
        curve_data = curve_obj.data
        
        # Bevel Depth setzen (Dicke)
        # Korrekturfaktor 0.5, da der Radius nach Konvertierung sonst doppelt so groß ist
        base_depth = shape_data['radius_scale'] * 0.5
        curve_data.bevel_depth = base_depth
        
        # Bevel Resolution setzen
        resolution = self._calculate_bevel_resolution(particle_count)
        curve_data.bevel_resolution = resolution
        
        # Fill Mode für geschlossenes Profil
        curve_data.fill_mode = 'FULL'
        
        # Längs-Profil: Dicke für jeden Punkt der Splines anpassen
        root_radius = shape_data['root_radius']
        tip_radius = shape_data['tip_radius']
        shape = shape_data['shape']
        
        for spline in curve_data.splines:
            point_count = len(spline.bezier_points) if spline.type == 'BEZIER' else len(spline.points)
            
            if point_count == 0:
                continue
            
            # Für jeden Punkt entlang der Kurve
            points = spline.bezier_points if spline.type == 'BEZIER' else spline.points
            
            for i, point in enumerate(points):
                # Normalisierte Position entlang der Kurve (0.0 = root, 1.0 = tip)
                t = i / (point_count - 1) if point_count > 1 else 0.0
                
                # Shape-Kurve anwenden (-1.0 = spitz, 0.0 = linear, 1.0 = stumpf)
                if shape < 0.0:
                    # Spitz: Kurve wird schneller dünner
                    t_shaped = t ** (1.0 - shape)
                elif shape > 0.0:
                    # Stumpf: Kurve bleibt länger dick
                    t_shaped = 1.0 - ((1.0 - t) ** (1.0 + shape))
                else:
                    # Linear
                    t_shaped = t
                
                # Radius interpolieren zwischen root und tip
                radius = root_radius * (1.0 - t_shaped) + tip_radius * t_shaped
                
                # Radius setzen
                if spline.type == 'BEZIER':
                    point.radius = radius
                else:
                    point.radius = radius
        
        self._log('INFO', f"Hair-Profil angewendet: Bevel Depth={base_depth:.4f}, Resolution={resolution}")
    
    def has_hair_particles(self, obj):
        """
        Prüft ob ein Objekt sichtbare Hair-Partikel hat (Path oder Object Rendering)
        
        Args:
            obj: Das zu prüfende Objekt
            
        Returns:
            bool: True wenn sichtbare Hair-Partikel vorhanden sind
        """
        if not obj or obj.type != 'MESH':
            return False
        
        # Prüfe über die Modifier, da dort die Sichtbarkeit gespeichert ist
        for modifier in obj.modifiers:
            if modifier.type == 'PARTICLE_SYSTEM' and modifier.show_viewport:
                if hasattr(modifier, 'particle_system'):
                    ps = modifier.particle_system
                    settings = ps.settings
                    if settings.type == 'HAIR' and settings.render_type in ['PATH', 'OBJECT']:
                        return True
        
        return False
    
    def _convert_object_hair_particles(self, context, obj, ps):
        """
        Konvertiert Hair-Partikel mit Object-Rendering zu echten Objekten
        
        Args:
            context: Blender Context
            obj: Das Objekt mit Hair-Partikeln
            ps: Das Partikel-System
            
        Returns:
            list: Liste der erstellten Objekte
        """
        settings = ps.settings
        
        # Partikelanzahl ermitteln - kann bei Hair-Systemen unterschiedlich sein
        try:
            particle_count = len(ps.particles)
        except:
            particle_count = settings.count if hasattr(settings, 'count') else 0
        
        self._log('INFO', f"Konvertiere Object-Hair-Partikel-System '{ps.name}' mit {particle_count} Partikeln (Settings count: {settings.count if hasattr(settings, 'count') else 'N/A'})")
        
        try:
            # Objekt muss selektiert und aktiv sein
            context.view_layer.objects.active = obj
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            
            # Alle Partikel-Systeme temporär verstecken, außer dem gewünschten
            # Dazu müssen wir die entsprechenden Modifier deaktivieren
            particle_modifiers_visibility = []
            for modifier in obj.modifiers:
                if modifier.type == 'PARTICLE_SYSTEM':
                    # Viewport-Sichtbarkeit merken
                    show_viewport = modifier.show_viewport
                    particle_modifiers_visibility.append((modifier, show_viewport))
                    
                    # Prüfen ob dieser Modifier zum aktuellen Partikel-System gehört
                    if hasattr(modifier, 'particle_system') and modifier.particle_system == ps:
                        # Dieses System sichtbar lassen
                        modifier.show_viewport = True
                    else:
                        # Andere verstecken
                        modifier.show_viewport = False
            
            # Aktuelle Objekte in der Szene merken (vor der Konvertierung)
            objects_before = set(context.scene.objects)
            
            # "Make Instances Real" - erstellt echte Objekte aus den Partikel-Instanzen
            # Da nur ein Partikel-System sichtbar ist, werden nur dessen Instanzen konvertiert
            bpy.ops.object.duplicates_make_real()
            
            # Neue Objekte identifizieren (nach der Konvertierung)
            objects_after = set(context.scene.objects)
            new_objects = list(objects_after - objects_before)
            
            # Modifier Sichtbarkeit wiederherstellen
            for modifier, show_viewport in particle_modifiers_visibility:
                modifier.show_viewport = show_viewport
            
            self._log('INFO', f"Object-Hair-Partikel '{ps.name}' erfolgreich konvertiert: {len(new_objects)} Objekte erstellt")
            
            return new_objects
            
        except Exception as e:
            # Modifier Sichtbarkeit im Fehlerfall wiederherstellen
            try:
                for modifier, show_viewport in particle_modifiers_visibility:
                    modifier.show_viewport = show_viewport
            except:
                pass
            
            self._log('WARNING', f"Fehler beim Konvertieren von Object-Hair-Partikel '{ps.name}': {e}")
            return []
    
    def convert_hair_particles(self, context, obj):
        """
        Konvertiert alle Hair-Partikel eines Objekts
        - PATH: zu Kurven mit Profil
        - OBJECT: zu echten Objekten (make instances real)
        
        Args:
            context: Blender Context
            obj: Das Objekt mit Hair-Partikeln
            
        Returns:
            list: Liste der erstellten Objekte
        """
        if not self.has_hair_particles(obj):
            return []
        
        # Objekt muss aktiv sein für die Konvertierung
        old_active = context.view_layer.objects.active
        old_selection = [o for o in context.selected_objects]
        
        try:
            # Objekt aktivieren und selektieren
            context.view_layer.objects.active = obj
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            
            converted_objects = []
            
            # Alle sichtbaren Hair-Partikel-Systeme durchgehen
            for modifier in obj.modifiers:
                if modifier.type != 'PARTICLE_SYSTEM' or not modifier.show_viewport:
                    continue
                
                if not hasattr(modifier, 'particle_system'):
                    continue
                
                ps = modifier.particle_system
                settings = ps.settings
                
                if settings.type != 'HAIR':
                    continue
                
                # OBJECT Render-Typ: Make Instances Real
                if settings.render_type == 'OBJECT':
                    new_objects = self._convert_object_hair_particles(context, obj, ps)
                    converted_objects.extend(new_objects)
                    continue
                
                # PATH Render-Typ: Zu Kurven konvertieren
                if settings.render_type != 'PATH':
                    continue
                
                # Shape-Daten und Material vor der Konvertierung extrahieren
                particle_count = len(ps.particles)
                shape_data = self._get_hair_shape_data(obj, ps)
                hair_material = self._get_hair_material(obj, ps)
                
                self._log('INFO', f"Konvertiere Hair-Partikel-System '{ps.name}' mit {particle_count} Partikeln")
                
                # Particle System Index finden
                ps_index = -1
                for i, particle_system in enumerate(obj.particle_systems):
                    if particle_system == ps:
                        ps_index = i
                        break
                
                if ps_index == -1:
                    self._log('WARNING', f"Konnte Particle System Index nicht finden")
                    continue
                
                try:
                    # Schritt 1: Hair zu Mesh konvertieren
                    bpy.ops.object.modifier_convert(modifier=ps.name)
                    
                    # Das konvertierte Mesh sollte jetzt das aktive Objekt sein
                    mesh_obj = context.active_object
                    
                    if mesh_obj and mesh_obj.type == 'MESH':
                        # Schritt 2: Mesh zu Curve konvertieren
                        bpy.ops.object.convert(target='CURVE')
                        
                        # Jetzt haben wir ein Kurven-Objekt
                        curve_obj = context.active_object
                        
                        if curve_obj and curve_obj.type == 'CURVE':
                            # Schritt 3: Profil anwenden
                            self._apply_hair_profile_to_curve(curve_obj, shape_data, particle_count)
                            
                            # Schritt 4: Material zuweisen
                            if hair_material:
                                self._apply_material_to_curve(curve_obj, hair_material)
                            
                            # Namen anpassen
                            curve_obj.name = f"{obj.name}_Hair_{ps.name}"
                            
                            converted_objects.append(curve_obj)
                            self._log('INFO', f"Path-Hair-Partikel '{ps.name}' erfolgreich konvertiert")
                        else:
                            self._log('WARNING', f"Konvertierung zu Curve fehlgeschlagen für '{ps.name}'")
                    else:
                        self._log('WARNING', f"Konvertierung zu Mesh fehlgeschlagen für '{ps.name}'")
                        
                except Exception as e:
                    self._log('WARNING', f"Fehler beim Konvertieren von Path-Hair-Partikel '{ps.name}': {e}")
                    continue
            
            return converted_objects
            
        finally:
            # Selektion und aktives Objekt wiederherstellen
            bpy.ops.object.select_all(action='DESELECT')
            for o in old_selection:
                try:
                    o.select_set(True)
                except:
                    pass
            context.view_layer.objects.active = old_active


def convert_hair_particles_for_object(context, obj, report_callback=None):
    """
    Convenience-Funktion zum Konvertieren von Hair-Partikeln
    - PATH: zu Kurven mit Profil
    - OBJECT: zu echten Objekten (make instances real)
    
    Args:
        context: Blender Context
        obj: Das Objekt mit Hair-Partikeln
        report_callback: Optional callback für Statusmeldungen
        
    Returns:
        list: Liste der erstellten Objekte
    """
    converter = HairParticleConverter(report_callback)
    return converter.convert_hair_particles(context, obj)

