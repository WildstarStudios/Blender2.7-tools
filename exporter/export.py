bl_info = {
    "name": "Advanced Auto-Exporter",
    "author": "WildStar Studios", 
    "version": (2, 4, 2),
    "blender": (2, 79, 0),
    "location": "View3D > Tool Shelf > Export",
    "description": "Advanced export with enhanced compatibility and visibility controls",
    "category": "Import-Export",
}

import bpy
import os
import re
import json
import datetime
from bpy.props import StringProperty, BoolProperty, EnumProperty, FloatProperty
from bpy.app.handlers import persistent
import mathutils
from mathutils import Vector

# ===== GLOBAL EXPORT STATE =====
class ExportState:
    """Global state to track export status"""
    is_exporting = False

# ===== 2.79b COMPATIBILITY SHIMS =====
def get_blender_version():
    """Get Blender version as tuple"""
    return bpy.app.version

def is_blender_version_or_newer(major, minor=0, patch=0):
    """Check if running on specified Blender version or newer"""
    return bpy.app.version >= (major, minor, patch)

def get_selected_ids_compat(context):
    """2.79b compatible selection getter"""
    selected_objects = context.selected_objects
    
    return {'objects': selected_objects}

def temp_override_compat(**kwargs):
    """2.79b compatible context override - simplified"""
    class DummyContext:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
    return DummyContext()

# ===== ENHANCED OPERATORS =====
class ADVANCED_GLB_OT_export(bpy.types.Operator):
    bl_idname = "export_scene.advanced_glb"
    bl_label = "Export"
    bl_description = "Export using current settings"
    bl_options = {'REGISTER'}

    def invoke(self, context, event):
        """Show confirmation dialog if enabled in preferences"""
        prefs = context.user_preferences.addons[__name__].preferences
        if prefs.enable_export_confirmation:
            return context.window_manager.invoke_props_dialog(self)
        else:
            return self.execute(context)

    def draw(self, context):
        layout = self.layout
        scene_props = context.scene.advanced_glb_props
        
        layout.label("Confirm Export")
        
        # Show export summary
        stats = self.get_export_stats(scene_props)
        for stat in stats:
            layout.label(stat)
        
        if scene_props.export_scope == 'SCENE':
            clean_name, _ = parse_modifiers(scene_props.scene_export_filename)
            layout.label("File: %s%s" % (clean_name, get_extension(scene_props.export_format)))
        else:
            layout.label("Scope: %ss" % scene_props.export_scope.title())
        
        layout.label("Mode: %s" % scene_props.export_mode.title())
        
        # Animation support warning - check both global and object-level animation settings
        if self.should_warn_about_animation(scene_props):
            if not does_format_support_animation(scene_props.export_format):
                layout.label("WARNING: %s format doesn't support animations!" % scene_props.export_format, icon='ERROR')

    def should_warn_about_animation(self, scene_props):
        """Check if we should warn about animation compatibility"""
        # Check global animation setting
        if scene_props.apply_animations:
            return True
            
        # Check if any objects have -anim modifier
        for obj in bpy.data.objects:
            if should_export_object(obj, scene_props.export_mode):
                clean_name, modifiers = parse_modifiers(obj.name)
                if modifiers['anim']:
                    return True
                    
        return False

    def get_export_stats(self, scene_props):
        """Get export statistics for confirmation dialog"""
        stats = []
        export_mode = scene_props.export_mode
        
        if scene_props.export_scope == 'SCENE':
            objects = [obj for obj in bpy.data.objects if should_export_object(obj, export_mode)]
            stats.append("Objects to export: %d" % len(objects))
        elif scene_props.export_scope == 'PARENT':
            parent_roots = find_parent_export_roots(export_mode)
            object_count = sum(len(objects) for objects in parent_roots.values())
            stats.append("Parent roots to export: %d" % len(parent_roots))
            stats.append("Objects to export: %d" % object_count)
        elif scene_props.export_scope == 'LAYER':
            layers = find_layer_export_roots(export_mode)
            object_count = sum(len(objects) for objects in layers.values())
            stats.append("Layers to export: %d" % len(layers))
            stats.append("Objects to export: %d" % object_count)
        elif scene_props.export_scope == 'OBJECT':
            objects = [obj for obj in bpy.data.objects if should_export_object(obj, export_mode)]
            stats.append("Objects to export: %d" % len(objects))
            
        return stats

    def execute(self, context):
        scene_props = context.scene.advanced_glb_props
        
        if ExportState.is_exporting:
            self.report({'WARNING'}, "Export already in progress. Please wait.")
            return {'CANCELLED'}
        
        # Animation warnings - check both global and object-level
        if self.should_warn_about_animation(scene_props):
            if not does_format_support_animation(scene_props.export_format):
                self.report({'WARNING'}, "%s format doesn't support animations!" % scene_props.export_format)
        
        ExportState.is_exporting = True
        try:
            result = export_main(context)
            if result == {'FINISHED'}:
                mode_display = scene_props.export_mode.title()
                self.report({'INFO'}, "Exported %s %s to %s" % (mode_display, scene_props.export_scope.lower(), scene_props.export_path))
            return result
        finally:
            ExportState.is_exporting = False

class ADVANCED_GLB_OT_export_selected(bpy.types.Operator):
    bl_idname = "export_scene.advanced_glb_selected"
    bl_label = "Export Selected"
    bl_description = "Export only the currently selected objects or parent hierarchies"
    bl_options = {'REGISTER'}

    def invoke(self, context, event):
        """Show confirmation dialog if enabled in preferences"""
        prefs = context.user_preferences.addons[__name__].preferences
        if prefs.enable_export_confirmation:
            return context.window_manager.invoke_props_dialog(self)
        else:
            return self.execute(context)

    def draw(self, context):
        layout = self.layout
        scene_props = context.scene.advanced_glb_props
        
        layout.label("Confirm Selected Export")
        
        selected_items = get_selected_items(context)
        export_type = scene_props.selected_export_type
        
        obj_count = len(selected_items['objects'])
        
        layout.label("Export Type: %s" % export_type.title())
        layout.label("Selected Objects: %d" % obj_count)
        layout.label("Mode: %s" % scene_props.export_mode.title())
        
        # Animation support warning - check both global and object-level
        if self.should_warn_about_animation(scene_props, selected_items):
            if not does_format_support_animation(scene_props.export_format):
                layout.label("WARNING: %s format doesn't support animations!" % scene_props.export_format, icon='ERROR')

    def should_warn_about_animation(self, scene_props, selected_items):
        """Check if we should warn about animation compatibility for selected items"""
        # Check global animation setting
        if scene_props.apply_animations:
            return True
            
        # Check if any selected objects have -anim modifier
        for obj in selected_items['objects']:
            clean_name, modifiers = parse_modifiers(obj.name)
            if modifiers['anim']:
                return True
                    
        return False

    def execute(self, context):
        scene_props = context.scene.advanced_glb_props
        
        if ExportState.is_exporting:
            self.report({'WARNING'}, "Export already in progress. Please wait.")
            return {'CANCELLED'}
        
        selected_items = get_selected_items(context)
        
        if not selected_items['objects']:
            self.report({'WARNING'}, "No objects selected")
            return {'CANCELLED'}
        
        # Animation warnings
        if self.should_warn_about_animation(scene_props, selected_items):
            if not does_format_support_animation(scene_props.export_format):
                self.report({'WARNING'}, "%s format doesn't support animations!" % scene_props.export_format)
        
        ExportState.is_exporting = True
        try:
            result = export_selected(context, selected_items)
            if result == {'FINISHED'}:
                export_type = scene_props.selected_export_type
                if export_type == 'PARENT':
                    # Count parent roots in selection
                    parent_roots = get_selected_parent_roots(selected_items['objects'])
                    self.report({'INFO'}, "Exported %d parent hierarchies to %s" % (len(parent_roots), scene_props.export_path))
                else:
                    obj_count = len(selected_items['objects'])
                    self.report({'INFO'}, "Exported %d objects to %s" % (obj_count, scene_props.export_path))
            return result
        finally:
            ExportState.is_exporting = False

# ===== HIGHLIGHT OPERATOR =====
class ADVANCED_GLB_OT_highlight_exportable(bpy.types.Operator):
    bl_idname = "advanced_glb.highlight_exportable"
    bl_label = "Highlight Exportable"
    bl_description = "Select all objects that will be exported with current settings"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene_props = context.scene.advanced_glb_props
        export_mode = scene_props.export_mode
        
        # Deselect all first
        bpy.ops.object.select_all(action='DESELECT')
        
        objects_to_select = []
        
        if scene_props.export_scope == 'SCENE':
            # Select all exportable objects in the scene
            for obj in bpy.data.objects:
                if should_export_object(obj, export_mode):
                    objects_to_select.append(obj)
                            
        elif scene_props.export_scope == 'PARENT':
            # Select objects from exportable parent hierarchies
            parent_roots = find_parent_export_roots(export_mode)
            for parent_obj, objects in parent_roots.items():
                objects_to_select.extend(objects)
                            
        elif scene_props.export_scope == 'LAYER':
            # Select objects from ALL layers (not just active ones)
            layers = find_all_layers_with_objects(export_mode)
            for layer_index, objects in layers.items():
                objects_to_select.extend(objects)
                            
        elif scene_props.export_scope == 'OBJECT':
            # Select individual exportable objects
            for obj in bpy.data.objects:
                if should_export_object(obj, export_mode):
                    objects_to_select.append(obj)
        
        # Select the objects
        for obj in objects_to_select:
            obj.select = True
        
        # Set active object if any were selected
        if objects_to_select:
            context.scene.objects.active = objects_to_select[0]
            self.report({'INFO'}, "Selected %d exportable objects" % len(objects_to_select))
        else:
            self.report({'WARNING'}, "No exportable objects found with current settings")
            
        return {'FINISHED'}

# ===== ORDER 66 OPERATOR =====
class ADVANCED_GLB_OT_execute_order_66(bpy.types.Operator):
    bl_idname = "advanced_glb.execute_order_66"
    bl_label = "Execute Order 66"
    bl_description = "Delete orphaned files based on tracking data"
    bl_options = {'REGISTER'}
    
    # FIXED: Changed from type annotation to old-style property
    cleanup_empty_folders = BoolProperty(
        name="Cleanup Empty Folders",
        default=False,
        description="Also delete empty folders in export directory"
    )
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        layout.label("This will delete orphaned files.")
        layout.label("This action cannot be undone!")
        
        layout.prop(self, "cleanup_empty_folders")
        
        orphans = find_orphaned_files()
        if orphans:
            layout.label("Files to be deleted:")
            box = layout.box()
            for orphan in orphans[:10]:
                box.label("• %s" % os.path.basename(orphan))
            if len(orphans) > 10:
                box.label("... and %d more" % (len(orphans) - 10))
        else:
            layout.label("No orphaned files found.")
    
    def execute(self, context):
        deleted_files = cleanup_orphaned_files(self.cleanup_empty_folders)
        if deleted_files:
            self.report({'INFO'}, "Executed Order 66: Deleted %d orphaned files" % len(deleted_files))
        else:
            self.report({'INFO'}, "No orphaned files found to delete")
        return {'FINISHED'}

# ===== DELETE TRACK FILE OPERATOR =====
class ADVANCED_GLB_OT_delete_track_file(bpy.types.Operator):
    bl_idname = "advanced_glb.delete_track_file"
    bl_label = "Delete Track File"
    bl_description = "Delete the export tracking file for this blend file"
    bl_options = {'REGISTER'}
    
    # FIXED: Changed from type annotation to old-style property
    generate_template = BoolProperty(
        name="Generate New Template",
        default=True,
        description="Generate a new tracking file template after deletion"
    )
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        layout.label("Delete export tracking file?")
        layout.label("This will remove export history tracking.")
        
        track_file_path = get_track_file_path()
        if os.path.exists(track_file_path):
            layout.label("File: %s" % os.path.basename(track_file_path))
        else:
            layout.label("No track file found")
        
        layout.prop(self, "generate_template")
        if self.generate_template:
            layout.label("A new template will be generated.")
    
    def execute(self, context):
        track_file_path = get_track_file_path()
        file_exists = os.path.exists(track_file_path)
        
        if file_exists:
            os.remove(track_file_path)
            self.report({'INFO'}, "Deleted track file: %s" % os.path.basename(track_file_path))
        else:
            self.report({'WARNING'}, "No track file found")
        
        if self.generate_template:
            if generate_track_file_template():
                self.report({'INFO'}, "New tracking template generated")
            else:
                self.report({'WARNING'}, "Failed to generate tracking template")
        
        return {'FINISHED'}

# ===== VALIDATION OPERATORS =====
class ADVANCED_GLB_OT_show_validation_report(bpy.types.Operator):
    bl_idname = "advanced_glb.show_validation_report"
    bl_label = "Export Modifier Issues"
    bl_description = "Show validation issues found in export modifiers"
    bl_options = {'REGISTER'}
    
    # FIXED: Changed from type annotation to old-style property
    message = StringProperty(
        name="Message",
        default="",
        description="Validation report message"
    )
    
    # FIXED: Changed from type annotation to old-style property
    issues = StringProperty(
        name="Issues",
        default="",
        description="Formatted issues string"
    )
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=600)
    
    def draw(self, context):
        layout = self.layout
        
        layout.label(self.message)
        layout.separator()
        
        if self.issues:
            box = layout.box()
            issues_lines = self.issues.split('\n')
            for line in issues_lines:
                if line.strip():
                    box.label(line)
        
        layout.separator()
        layout.label("Please fix these issues before exporting.")
    
    def execute(self, context):
        return {'FINISHED'}

class ADVANCED_GLB_OT_validate_export_modifiers(bpy.types.Operator):
    bl_idname = "advanced_glb.validate_export_modifiers"
    bl_label = "Validate Export Modifiers"
    bl_description = "Check for incompatible modifier combinations and duplicates"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        prefs = context.user_preferences.addons[__name__].preferences
        issues = validate_export_modifiers(prefs.sk_behavior)
        
        if not issues:
            self.report({'INFO'}, "All modifiers are valid")
            return {'FINISHED'}
        
        formatted_issues = self.format_issues_for_display(issues)
        message = self.get_validation_message(issues)
        
        bpy.ops.advanced_glb.show_validation_report(
            'INVOKE_DEFAULT',
            message=message,
            issues=formatted_issues
        )
        
        return {'FINISHED'}
    
    def format_issues_for_display(self, issues):
        """Format issues into a readable string for the dialog"""
        if not issues:
            return "No issues found."
        
        formatted = []
        
        errors = [issue for issue in issues if issue['type'] == 'ERROR']
        warnings = [issue for issue in issues if issue['type'] == 'WARNING']
        
        if errors:
            formatted.append("ERRORS:")
            for error in errors:
                formatted.append("ERROR: %s" % error['message'])
            formatted.append("")
        
        if warnings:
            formatted.append("WARNINGS:")
            for warning in warnings:
                formatted.append("WARNING: %s" % warning['message'])
        
        return '\n'.join(formatted)
    
    def get_validation_message(self, issues):
        """Get the main validation message"""
        error_count = sum(1 for issue in issues if issue['type'] == 'ERROR')
        warning_count = sum(1 for issue in issues if issue['type'] == 'WARNING')
        
        if error_count > 0 and warning_count > 0:
            return "Found %d errors and %d warnings" % (error_count, warning_count)
        elif error_count > 0:
            return "Found %d errors" % error_count
        elif warning_count > 0:
            return "Found %d warnings" % warning_count
        else:
            return "No issues found"

# ===== ANIMATION SUPPORT CHECK =====
def does_format_support_animation(format_type):
    """Check if the format supports animations"""
    animation_supported_formats = {'FBX', 'DAE', 'X3D'}
    return format_type in animation_supported_formats

def get_animation_support_message(format_type):
    """Get animation support message for format"""
    if format_type == 'FBX':
        return "FBX: Full animation support"
    elif format_type == 'DAE':
        return "Collada: Good animation support" 
    elif format_type == 'X3D':
        return "X3D: Limited animation support"
    else:
        return "%s: No animation support" % format_type

def should_warn_about_animation(scene_props):
    """Check if we should warn about animation compatibility"""
    # Check global animation setting
    if scene_props.apply_animations:
        return True
        
    # Check if any objects have -anim modifier
    for obj in bpy.data.objects:
        if should_export_object(obj, scene_props.export_mode):
            clean_name, modifiers = parse_modifiers(obj.name)
            if modifiers['anim']:
                return True
                
    return False

# ===== ENHANCED PROPERTIES =====
class AdvancedGLBSceneProperties(bpy.types.PropertyGroup):
    # FIXED: All properties changed from type annotation to old-style
    export_path = StringProperty(
        name="Export Path",
        subtype='DIR_PATH',
        default="",
        description="Directory path for exports"
    )
    
    auto_export_on_save = BoolProperty(
        name="Auto Export on Save",
        default=True,
        description="Automatically export when saving the Blender file"
    )
    
    # CHANGED: Removed GROUP, added PARENT
    export_scope = EnumProperty(
        name="Export Scope",
        items=[
            ('SCENE', "Scene", "Export entire scene as one file"),
            ('PARENT', "Parents", "Export each parent hierarchy as individual files"),
            ('LAYER', "Layers", "Export each layer as individual files"),
            ('OBJECT', "Objects", "Export each object as individual files"),
        ],
        default='SCENE',
        description="Select how to organize the exported files"
    )
    
    export_mode = EnumProperty(
        name="Export Mode",
        items=[
            ('ALL', "All Objects", "Export all objects regardless of visibility"),
            ('VISIBLE', "Visible Only", "Export only visible objects"),
            ('RENDERABLE', "Render Only", "Export only renderable objects"),
        ],
        default='VISIBLE',
        description="Control which objects to export based on visibility and renderability"
    )
    
    selected_export_type = EnumProperty(
        name="Export Selected As",
        items=[
            ('PARENT', "Parent Hierarchies", "Export selected items as parent hierarchies"),
            ('OBJECT', "Objects", "Export selected items as individual objects"),
        ],
        default='PARENT',
        description="How to handle selected items export"
    )
    
    scene_export_filename = StringProperty(
        name="Scene Filename",
        default="scene",
        description="Filename for scene export (without extension)"
    )
    
    # UPDATED: Added animation-supported formats
    export_format = EnumProperty(
        name="Export Format",
        items=[
            ('FBX', "FBX", "FBX (.fbx) - Full animation support"),
            ('DAE', "Collada", "Collada DAE (.dae) - Good animation support"), 
            ('X3D', "X3D", "X3D (.x3d) - Limited animation support"),
            ('OBJ', "OBJ", "Wavefront OBJ (.obj) - No animation"),
            ('STL', "STL", "STL (.stl) - No animation"),
            ('PLY', "PLY", "PLY (.ply) - No animation"),
        ],
        default='FBX',
        description="Export file format"
    )
    
    export_up_axis = EnumProperty(
        name="Export Up Axis",
        items=[
            ('Y', "Y Up", "Y is up (standard for most applications)"),
            ('Z', "Z Up", "Z is up (Blender's default)"),
        ],
        default='Y',
        description="Up axis for all exports"
    )
    
    apply_animations = BoolProperty(
        name="Apply Animations",
        default=False,
        description="Include animations in export (if format supports it)"
    )

# ===== ENHANCED PREFERENCES =====
class AdvancedGLBPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    # FIXED: All properties changed from type annotation to old-style
    auto_export_on_save = BoolProperty(
        name="Auto Export on Save",
        default=True,
        description="Automatically export when saving the Blender file"
    )
    
    apply_modifiers = BoolProperty(
        name="Apply Modifiers",
        default=True,
        description="Apply modifiers before export"
    )
    
    export_individual_origins = BoolProperty(
        name="Export with Local Origins",
        default=True,
        description="Export each object/parent hierarchy with its local origin at (0,0,0) by moving to 3D cursor"
    )
    
    apply_animations = BoolProperty(
        name="Apply Animations",
        default=False,
        description="Include animations in export (if format supports it)"
    )
    
    enable_export_confirmation = BoolProperty(
        name="Enable Export Confirmation",
        default=True,
        description="Show confirmation dialog before exporting"
    )
    
    sk_behavior = EnumProperty(
        name="-sk Behavior",
        items=[
            ('BASIC', "Basic", "Skip parents without validation"),
            ('STRICT', "Strict", "Validate -sk usage and prevent export if issues found"),
        ],
        default='BASIC',
        description="How to handle -sk modifier validation"
    )
    
    show_detailed_list = BoolProperty(
        name="Show Export Preview",
        default=False,
        description="Show detailed preview of what will be exported"
    )
    
    show_hidden_objects = BoolProperty(
        name="Show Hidden in Preview",
        default=False,
        description="Include hidden objects in the export preview"
    )
    
    enable_export_tracking = BoolProperty(
        name="Enable Export Tracking",
        default=True,
        description="Track exported files to identify orphans. Uses .track files"
    )
    
    track_file_location = EnumProperty(
        name="Track File Location",
        items=[
            ('BLEND', "With Blend File", "Store track file with the .blend file"),
            ('EXPORT', "In Export Directory", "Store track file in the export directory")
        ],
        default='BLEND',
        description="Where to store the export tracking file"
    )

    def draw(self, context):
        layout = self.layout
        
        # Main settings
        main_box = layout.box()
        main_box.label("Export Behavior")
        main_box.prop(self, "auto_export_on_save")
        main_box.prop(self, "apply_modifiers")
        main_box.prop(self, "export_individual_origins")
        main_box.prop(self, "apply_animations")
        main_box.prop(self, "enable_export_confirmation")
        main_box.prop(self, "sk_behavior")
        
        # Display settings
        display_box = layout.box()
        display_box.label("Display Options")
        display_box.prop(self, "show_detailed_list")
        
        if self.show_detailed_list:
            display_box.prop(self, "show_hidden_objects")
        
        # Tracking settings
        track_box = layout.box()
        track_box.label("File Tracking")
        track_box.prop(self, "enable_export_tracking")
        
        if self.enable_export_tracking:
            track_box.prop(self, "track_file_location")
            
            row = track_box.row()
            row.operator("advanced_glb.execute_order_66", text="Clean Orphans")
            row.operator("advanced_glb.delete_track_file", text="Delete Track File")

# ===== ENHANCED UI PANEL =====
class ADVANCED_GLB_PT_panel(bpy.types.Panel):
    bl_label = "Advanced Auto-Export"
    bl_idname = "VIEW3D_PT_advanced_glb_export"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'
    bl_category = 'Export'

    def draw(self, context):
        layout = self.layout
        scene_props = context.scene.advanced_glb_props
        prefs = context.user_preferences.addons[__name__].preferences
        
        # === QUICK EXPORT SECTION ===
        quick_box = layout.box()
        
        # Export destination
        row = quick_box.row()
        row.label("Export To:")
        row = quick_box.row()
        row.prop(scene_props, "export_path", text="")
        
        if not scene_props.export_path:
            quick_box.label("Set export directory first")
            return
        
        # Format and Scope in one row
        row = quick_box.row(align=True)
        row.prop(scene_props, "export_format", text="")
        row.prop(scene_props, "export_scope", text="Scope")
        
        # Export Mode with highlight button
        mode_row = quick_box.row(align=True)
        mode_row.label("Export Mode:")
        mode_row.prop(scene_props, "export_mode", text="")
        mode_row.operator("advanced_glb.highlight_exportable", text="", icon='RESTRICT_SELECT_OFF')
        
        # Up Axis
        quick_box.prop(scene_props, "export_up_axis", expand=True)
        
        # Scene filename when in scene mode
        if scene_props.export_scope == 'SCENE':
            row = quick_box.row(align=True)
            row.label("Filename:")
            row.prop(scene_props, "scene_export_filename", text="")
        
        # Animation warnings and status - check both global and object-level
        if should_warn_about_animation(scene_props):
            if does_format_support_animation(scene_props.export_format):
                anim_row = quick_box.row()
                anim_row.label("Animations enabled", icon='ANIM')
            else:
                warning_row = quick_box.row()
                warning_row.label("WARNING: %s doesn't support animations!" % scene_props.export_format, icon='ERROR')
        
        # Stats with mode information
        stats = self.get_enhanced_quick_stats(scene_props)
        if stats:
            stats_box = quick_box.box()
            for stat in stats:
                stats_box.label(stat)
        
        # Export buttons
        button_text = self.get_enhanced_export_button_text(scene_props)
        
        if ExportState.is_exporting:
            export_row = quick_box.row()
            export_row.enabled = False
            export_row.operator("export_scene.advanced_glb", text="Exporting...")
            quick_box.label("Export in progress...")
        else:
            # Main export button
            export_row = quick_box.row()
            export_op = export_row.operator("export_scene.advanced_glb", text=button_text)
            
            # Selected export with dropdown
            selected_items = get_selected_items(context)
            if selected_items['objects']:
                select_box = quick_box.box()
                select_box.label("Export Selected:")
                
                row = select_box.row(align=True)
                row.prop(scene_props, "selected_export_type", expand=True)
                
                select_label = self.get_enhanced_select_export_label(selected_items, scene_props)
                select_box.operator("export_scene.advanced_glb_selected", text=select_label)
        
        # === SETTINGS SECTION ===
        settings_box = layout.box()
        settings_box.label("Settings")
        
        settings_box.prop(prefs, "auto_export_on_save")
        settings_box.prop(prefs, "apply_modifiers")
        
        local_origins_row = settings_box.row()
        local_origins_row.prop(prefs, "export_individual_origins")
        if scene_props.export_scope == 'SCENE':
            local_origins_row.enabled = False
        
        settings_box.prop(prefs, "apply_animations")
        settings_box.prop(prefs, "show_detailed_list", text="Show Export Preview")
        
        if prefs.show_detailed_list:
            settings_box.prop(prefs, "show_hidden_objects")
        
        # === MODIFIERS INFO ===
        mod_box = layout.box()
        mod_box.label("Name Modifiers")
        
        # FIXED: Changed grid_flow to column_flow for 2.79b compatibility
        mod_grid = mod_box.column_flow(columns=2, align=True)
        
        mod_grid.label("• -dir:folder → Organize in subfolder")
        mod_grid.label("• -sep → Export parent separately")
        mod_grid.label("• -dk → Don't export this item")  
        mod_grid.label("• -sk → Skip parent (ignore)")
        mod_grid.label("• -anim → Include animations")
        mod_grid.label("• Visibility → Controlled by Export Mode")
        
        # Validation button
        validation_row = mod_box.row()
        validation_row.operator("advanced_glb.validate_export_modifiers")
        
        if scene_props.export_scope == 'SCENE':
            validation_row.enabled = False
        
        # === TRACKING SYSTEM ===
        if prefs.enable_export_tracking:
            track_box = layout.box()
            track_box.label("File Tracking")
            
            track_box.prop(prefs, "track_file_location", expand=True)
            
            row = track_box.row(align=True)
            row.operator("advanced_glb.execute_order_66", text="Clean Orphans")
            row.operator("advanced_glb.delete_track_file", text="Delete Track File")
        
        # === EXPORT PREVIEW ===
        if prefs.show_detailed_list:
            preview_box = layout.box()
            preview_box.label("Export Preview")
            
            preview_box.label("Objects that will be exported:")
            
            details = self.get_enhanced_export_preview(scene_props, prefs)
            if details:
                for detail in details:
                    preview_box.label(detail)
            else:
                preview_box.label("No objects will be exported with current settings")

    def get_enhanced_quick_stats(self, scene_props):
        """Enhanced statistics with mode information"""
        if not scene_props.export_path:
            return []
            
        stats = []
        export_mode = scene_props.export_mode
        
        if ExportState.is_exporting:
            stats.append("Export in progress...")
            return stats
            
        if scene_props.export_scope == 'SCENE':
            objects = [obj for obj in bpy.data.objects if should_export_object(obj, export_mode)]
            stats.append("Scene (%s): %d objects" % (export_mode, len(objects)))
            
        elif scene_props.export_scope == 'PARENT':
            parent_roots = find_parent_export_roots(export_mode)
            object_count = sum(len(objects) for objects in parent_roots.values())
            stats.append("Parent roots (%s): %d" % (export_mode, len(parent_roots)))
            stats.append("Objects: %d" % object_count)
            
        elif scene_props.export_scope == 'LAYER':
            layers = find_all_layers_with_objects(export_mode)
            object_count = sum(len(objects) for objects in layers.values())
            stats.append("Layers (%s): %d" % (export_mode, len(layers)))
            stats.append("Objects: %d" % object_count)
            
        elif scene_props.export_scope == 'OBJECT':
            objects = [obj for obj in bpy.data.objects if should_export_object(obj, export_mode)]
            stats.append("Objects (%s): %d" % (export_mode, len(objects)))
            
        return stats

    def get_enhanced_export_button_text(self, scene_props):
        """Enhanced export button text with mode info"""
        if ExportState.is_exporting:
            return "Exporting..."
        
        mode_text = scene_props.export_mode.title()
        if scene_props.export_scope == 'SCENE':
            clean_name, _ = parse_modifiers(scene_props.scene_export_filename)
            return "Export %s %s" % (mode_text, clean_name)
        else:
            scope_text = scene_props.export_scope.title()
            return "Export %s %ss" % (mode_text, scope_text)

    def get_enhanced_select_export_label(self, selected_items, scene_props):
        """Enhanced selected export label with type info"""
        obj_count = len(selected_items['objects'])
        export_type = scene_props.selected_export_type
        
        if export_type == 'PARENT':
            parent_roots = get_selected_parent_roots(selected_items['objects'])
            return "Export (%d parent hierarchies)" % len(parent_roots)
        else:  # OBJECT
            return "Export (%d objects)" % obj_count

    def get_enhanced_export_preview(self, scene_props, prefs):
        """Enhanced export preview with better organization"""
        details = []
        export_mode = scene_props.export_mode
        
        if scene_props.export_scope == 'SCENE':
            objects = [obj for obj in bpy.data.objects if should_export_object(obj, export_mode)]
            clean_name, modifiers = parse_modifiers(scene_props.scene_export_filename)
            
            details.append("File: %s%s" % (clean_name, get_extension(scene_props.export_format)))
            if modifiers.get('dir'):
                details.append("Directory: %s" % modifiers['dir'])
            
            # Show objects that will be exported
            if objects:
                details.append("Objects to export:")
                for obj in objects[:8]:  # Show first 8 objects
                    obj_clean, _ = parse_modifiers(obj.name)
                    details.append("  • %s" % obj_clean)
                if len(objects) > 8:
                    details.append("  ... and %d more" % (len(objects) - 8))
            else:
                details.append("No objects will be exported")

        elif scene_props.export_scope == 'PARENT':
            parent_roots = find_parent_export_roots(export_mode)
            if parent_roots:
                details.append("Parent hierarchies to export (%s):" % export_mode)
                
                for parent_obj, objects in parent_roots.items():
                    clean_name, modifiers = parse_modifiers(parent_obj.name)
                    dir_info = " → %s" % modifiers['dir'] if modifiers.get('dir') else ""
                    details.append("• %s%s: %d objects" % (clean_name, dir_info, len(objects)))
            else:
                details.append("No parent hierarchies will be exported")

        elif scene_props.export_scope == 'LAYER':
            layers = find_all_layers_with_objects(export_mode)
            if layers:
                details.append("Layers to export (%s):" % export_mode)
                
                for layer_index, objects in layers.items():
                    details.append("• Layer %d: %d objects" % (layer_index + 1, len(objects)))
            else:
                details.append("No layers will be exported")

        elif scene_props.export_scope == 'OBJECT':
            objects = [obj for obj in bpy.data.objects if should_export_object(obj, export_mode)]
            if objects:
                details.append("Objects to export (%s):" % export_mode)
                
                for obj in objects[:8]:  # Show first 8 objects
                    clean_name, modifiers = parse_modifiers(obj.name)
                    details.append("• %s" % clean_name)
                    
                if len(objects) > 8:
                    details.append("  ... and %d more" % (len(objects) - 8))
            else:
                details.append("No objects will be exported")
                
        return details

# ===== 2.79b COMPATIBILITY FUNCTIONS =====

def is_object_visible(obj, mode='VISIBLE'):
    """
    2.79b compatible visibility checking
    """
    if mode == 'ALL':
        return True
    elif mode == 'VISIBLE':
        # In 2.79b, check hide and hide_render properties
        return not (obj.hide or obj.hide_render)
    elif mode == 'RENDERABLE':
        # Only objects that are not hidden from render
        return not obj.hide_render
    return True

def should_export_object(obj, export_mode='VISIBLE'):
    """
    2.79b compatible object export decision
    """
    clean_name, modifiers = parse_modifiers(obj.name)
    
    # Always exclude objects with -dk modifier
    if modifiers['dk']:
        return False
    
    # Check object type compatibility
    if obj.type not in {'MESH', 'CURVE', 'SURFACE', 'META', 'FONT', 'ARMATURE'}:
        return False
    
    # Use visibility system based on export mode
    return is_object_visible(obj, export_mode)

# ===== PARENT-BASED SYSTEM FUNCTIONS =====

def get_object_children(obj):
    """Get all children of an object recursively"""
    children = []
    for child in bpy.data.objects:
        if child.parent == obj:
            children.append(child)
            children.extend(get_object_children(child))
    return children

def get_object_hierarchy(obj):
    """Get the entire hierarchy starting from an object (parent + children)"""
    hierarchy = [obj]
    hierarchy.extend(get_object_children(obj))
    return hierarchy

def is_root_object(obj):
    """Check if object is a root (no parent or parent shouldn't be exported)"""
    if not obj.parent:
        return True
    
    # Check if parent has -dk modifier
    parent_clean, parent_modifiers = parse_modifiers(obj.parent.name)
    if parent_modifiers['dk']:
        return True
    
    # Check if parent is not visible in current export mode
    if not should_export_object(obj.parent):
        return True
    
    return False

def find_parent_export_roots(export_mode='VISIBLE'):
    """Find parent export roots based on object hierarchies"""
    export_parents = {}
    
    for obj in bpy.data.objects:
        # Skip objects that shouldn't be exported
        if not should_export_object(obj, export_mode):
            continue
            
        # Check if this is a root object for export
        if is_root_object(obj):
            clean_name, modifiers = parse_modifiers(obj.name)
            
            # Skip objects with -dk or -sk modifiers
            if modifiers['dk'] or modifiers['sk']:
                continue
                
            # Get the entire hierarchy
            hierarchy = get_object_hierarchy(obj)
            
            # Filter hierarchy to only include exportable objects
            exportable_hierarchy = [child for child in hierarchy if should_export_object(child, export_mode)]
            
            if exportable_hierarchy:
                export_parents[obj] = exportable_hierarchy
    
    return export_parents

def get_selected_parent_roots(selected_objects):
    """Get parent roots from selected objects"""
    parent_roots = {}
    
    for obj in selected_objects:
        # Find the root parent of this object
        root_obj = obj
        while root_obj.parent and root_obj.parent in selected_objects:
            root_obj = root_obj.parent
        
        if root_obj not in parent_roots:
            parent_roots[root_obj] = get_object_hierarchy(root_obj)
    
    return parent_roots

def find_all_layers_with_objects(export_mode='VISIBLE'):
    """Find ALL layers with objects (not just active ones) - 2.79b compatible"""
    export_layers = {}
    
    # Blender 2.79b has 20 layers
    for layer_index in range(20):
        layer_objects = []
        for obj in bpy.data.objects:
            # Check if object is in this layer and should be exported
            # In 2.79b, obj.layers is a 20-element boolean array
            if obj.layers[layer_index] and should_export_object(obj, export_mode):
                layer_objects.append(obj)
        
        if layer_objects:
            export_layers[layer_index] = layer_objects
    
    return export_layers

def find_layer_export_roots(export_mode='VISIBLE'):
    """Find layer export roots in 2.79b - uses ALL layers, not just active ones"""
    return find_all_layers_with_objects(export_mode)

# ===== TRACKING SYSTEM =====
def update_track_file(exported_files, export_path):
    """Enhanced tracking that includes export settings for better cleanup"""
    prefs = bpy.context.user_preferences.addons[__name__].preferences
    if not prefs.enable_export_tracking:
        return
    
    scene_props = bpy.context.scene.advanced_glb_props
    track_data = load_track_data()
    
    # Create a unique key based on export settings to handle scope/mode changes
    settings_key = "%s|%s|%s" % (export_path, scene_props.export_scope, scene_props.export_mode)
    
    if settings_key not in track_data:
        track_data[settings_key] = {}
    
    # Store current export settings along with files
    track_data[settings_key]['last_export'] = {
        'timestamp': datetime.datetime.now().isoformat(),
        'files': exported_files,
        'blend_file': bpy.data.filepath or "unsaved",
        'format': scene_props.export_format,
        'scope': scene_props.export_scope,
        'mode': scene_props.export_mode,
        'export_path': export_path
    }
    
    if 'history' not in track_data[settings_key]:
        track_data[settings_key]['history'] = []
    
    track_data[settings_key]['history'].append({
        'timestamp': datetime.datetime.now().isoformat(),
        'files': exported_files,
        'format': scene_props.export_format,
        'scope': scene_props.export_scope,
        'mode': scene_props.export_mode
    })
    
    # Keep only last 10 history entries
    track_data[settings_key]['history'] = track_data[settings_key]['history'][-10:]
    
    save_track_data(track_data)

def find_orphaned_files():
    """Enhanced orphan detection that considers export settings changes"""
    track_data = load_track_data()
    orphans = []
    
    # Get all currently tracked files across all export settings
    all_tracked_files = set()
    current_export_paths = set()
    
    for settings_key, path_data in track_data.items():
        if 'last_export' in path_data:
            all_tracked_files.update(path_data['last_export']['files'])
            # Extract export path from settings key
            export_path = path_data['last_export'].get('export_path', settings_key.split('|')[0])
            current_export_paths.add(export_path)
    
    # Check all current export paths for orphaned files
    for export_path in current_export_paths:
        if not os.path.exists(export_path):
            continue
            
        # Get all files in export directory and subdirectories
        current_files = set()
        supported_extensions = {'.obj', '.fbx', '.stl', '.ply', '.dae', '.x3d'}
        
        for root, dirs, files in os.walk(export_path):
            # Skip track files themselves
            if root.endswith('.export.track'):
                continue
                
            for file in files:
                file_ext = os.path.splitext(file)[1].lower()
                if file_ext in supported_extensions:
                    full_path = os.path.join(root, file)
                    current_files.add(full_path)
        
        # Find files that exist but aren't tracked
        for file_path in current_files:
            if file_path not in all_tracked_files:
                orphans.append(file_path)
    
    return orphans

def cleanup_orphaned_files(cleanup_empty_folders=False):
    """Enhanced cleanup with optional empty folder removal"""
    orphans = find_orphaned_files()
    deleted_files = []
    deleted_folders = []
    
    for orphan in orphans:
        try:
            base_name = os.path.splitext(orphan)[0]
            parent_dir = os.path.dirname(orphan)
            
            os.remove(orphan)
            deleted_files.append(orphan)
            print("Deleted orphaned file: %s" % orphan)
            
        except Exception as e:
            print("Failed to delete %s: %s" % (orphan, str(e)))
    
    # Optional empty folder cleanup
    if cleanup_empty_folders:
        deleted_folders = cleanup_empty_folders_func()
    
    # Update track data to remove references to deleted files
    track_data = load_track_data()
    for settings_key, path_data in track_data.items():
        if 'last_export' in path_data:
            path_data['last_export']['files'] = [
                f for f in path_data['last_export']['files'] 
                if f not in deleted_files and os.path.exists(f)
            ]
        
        if 'history' in path_data:
            for history_entry in path_data['history']:
                history_entry['files'] = [
                    f for f in history_entry['files']
                    if f not in deleted_files and os.path.exists(f)
                ]
    
    save_track_data(track_data)
    
    if cleanup_empty_folders and deleted_folders:
        print("Deleted %d empty folders" % len(deleted_folders))
    
    return deleted_files

def cleanup_empty_folders_func():
    """Remove empty folders from export directories"""
    deleted_folders = []
    track_data = load_track_data()
    
    # Get all export paths from track data
    export_paths = set()
    for settings_key, path_data in track_data.items():
        if 'last_export' in path_data:
            export_path = path_data['last_export'].get('export_path', settings_key.split('|')[0])
            if os.path.exists(export_path):
                export_paths.add(export_path)
    
    for export_path in export_paths:
        # Walk through all subdirectories and remove empty ones
        for root, dirs, files in os.walk(export_path, topdown=False):
            # Skip if this is the root export path
            if root == export_path:
                continue
                
            # Check if directory is empty (no files and no subdirectories)
            if not os.listdir(root):
                try:
                    os.rmdir(root)
                    deleted_folders.append(root)
                    print("Deleted empty folder: %s" % root)
                except Exception as e:
                    print("Failed to delete empty folder %s: %s" % (root, str(e)))
    
    return deleted_folders

# ===== UTILITY FUNCTIONS =====
def get_selected_items(context):
    """Get selected objects - 2.79b COMPATIBLE"""
    return get_selected_ids_compat(context)

def get_extension(format_type):
    """Get file extension for format"""
    extensions = {
        'OBJ': '.obj',
        'FBX': '.fbx',
        'STL': '.stl',
        'PLY': '.ply',
        'DAE': '.dae',
        'X3D': '.x3d'
    }
    return extensions.get(format_type, '.obj')

def check_operator_exists(operator_name):
    """Check if an operator exists - 2.79b COMPATIBLE"""
    try:
        op_name = operator_name.split('.')[-1]
        return hasattr(bpy.ops, op_name)
    except:
        return False

def get_available_export_operators():
    """Get available export operators - 2.79b COMPATIBLE"""
    available_ops = {}
    
    test_operators = {
        'OBJ': ['export_scene.obj', 'export_mesh.obj'],
        'FBX': ['export_scene.fbx'],
        'STL': ['export_mesh.stl'],
        'PLY': ['export_mesh.ply'],
        'DAE': ['wm.collada_export'],
        'X3D': ['export_scene.x3d']
    }
    
    for format_type, operators in test_operators.items():
        for op in operators:
            if check_operator_exists(op):
                available_ops[format_type] = op
                break
    
    return available_ops

def export_obj_compat(filepath, use_selection=False, apply_modifiers=True):
    """
    2.79b compatible OBJ export
    """
    try:
        scene_props = bpy.context.scene.advanced_glb_props
        
        # 2.79b uses export_scene.obj with different parameters
        export_params = {
            'filepath': filepath,
            'use_selection': use_selection,
            'use_mesh_modifiers': apply_modifiers,
            'use_normals': True,
            'use_uvs': True,
            'use_materials': True,
            'use_triangles': False,
            'use_nurbs': False,
            'use_vertex_groups': False,
            'use_blen_objects': True,
            'group_by_object': False,
            'group_by_material': False,
            'keep_vertex_order': False,
            'global_scale': 1.0,
            'path_mode': 'AUTO',
            'axis_forward': '-Z',
            'axis_up': 'Y' if scene_props.export_up_axis == 'Y' else 'Z'
        }
        
        bpy.ops.export_scene.obj(**export_params)
        print("Exported OBJ to: %s" % filepath)
        return True
            
    except Exception as e:
        print("OBJ export failed: %s" % str(e))
        return False

def parse_modifiers(name):
    """Parse modifiers from name and return clean name + modifiers dict"""
    modifiers = {
        'dir': None,
        'sep': False,
        'dk': False,
        'sk': False,
        'anim': False
    }
    
    clean_name = name.strip()
    
    # Extract -dir modifier first (only use the first one found)
    dir_match = re.search(r'[\s\-]dir:([^\s]+)', clean_name, re.IGNORECASE)
    if dir_match:
        modifiers['dir'] = dir_match.group(1).strip()
        # Remove ALL -dir instances from the clean name
        clean_name = re.sub(r'[\s\-]dir:[^\s]+', '', clean_name, flags=re.IGNORECASE).strip()
    
    # Count occurrences of each modifier
    sk_count = len(re.findall(r'[\s\-]sk', clean_name, re.IGNORECASE))
    dk_count = len(re.findall(r'[\s\-]dk', clean_name, re.IGNORECASE))
    sep_count = len(re.findall(r'[\s\-]sep', clean_name, re.IGNORECASE))
    anim_count = len(re.findall(r'[\s\-]anim', clean_name, re.IGNORECASE))
    
    # Set flags based on presence (any count > 0)
    modifiers['sep'] = sep_count > 0
    modifiers['dk'] = dk_count > 0  
    modifiers['sk'] = sk_count > 0
    modifiers['anim'] = anim_count > 0
    
    # Remove all modifier instances from the clean name
    clean_name = re.sub(r'[\s\-]sep', '', clean_name, flags=re.IGNORECASE).strip()
    clean_name = re.sub(r'[\s\-]dk', '', clean_name, flags=re.IGNORECASE).strip()
    clean_name = re.sub(r'[\s\-]sk', '', clean_name, flags=re.IGNORECASE).strip()
    clean_name = re.sub(r'[\s\-]anim', '', clean_name, flags=re.IGNORECASE).strip()
    
    clean_name = re.sub(r'\s+', ' ', clean_name).strip()
    
    return clean_name, modifiers

def get_parent_center(parent_objects):
    """Calculate the center point of all objects in a parent hierarchy"""
    if not parent_objects:
        return Vector((0, 0, 0))
    
    total_position = Vector((0, 0, 0))
    valid_objects = 0
    
    for obj in parent_objects:
        if obj and obj.matrix_world:
            total_position += obj.matrix_world.translation
            valid_objects += 1
    
    if valid_objects == 0:
        return Vector((0, 0, 0))
    
    return total_position / valid_objects

def move_parent_to_origin(parent_objects, cursor_location):
    """Move entire parent hierarchy to cursor while maintaining relative positions"""
    if not parent_objects:
        return {}
    
    original_positions = {}
    for obj in parent_objects:
        if obj:
            original_positions[obj] = obj.matrix_world.copy()
    
    parent_center = get_parent_center(parent_objects)
    offset = cursor_location - parent_center
    
    for obj in parent_objects:
        if obj:
            new_position = obj.matrix_world.translation + offset
            obj.matrix_world.translation = new_position
    
    return original_positions

def restore_parent_positions(original_positions):
    """Restore parent hierarchy objects to their original positions"""
    for obj, original_matrix in original_positions.items():
        if obj:
            obj.matrix_world = original_matrix

def get_track_file_path():
    """Get the path for the track file based on preferences"""
    prefs = bpy.context.user_preferences.addons[__name__].preferences
    
    if prefs.track_file_location == 'EXPORT':
        scene_props = bpy.context.scene.advanced_glb_props
        if scene_props.export_path:
            if bpy.data.filepath:
                blend_name = os.path.splitext(os.path.basename(bpy.data.filepath))[0]
            else:
                blend_name = "unsaved"
            return os.path.join(scene_props.export_path, "%s.export.track" % blend_name)
        else:
            return get_blend_track_file_path()
    else:
        return get_blend_track_file_path()

def get_blend_track_file_path():
    """Get track file path in blend file directory"""
    if bpy.data.filepath:
        blend_name = os.path.splitext(os.path.basename(bpy.data.filepath))[0]
        return os.path.join(os.path.dirname(bpy.data.filepath), "%s.export.track" % blend_name)
    else:
        return os.path.join(os.path.expanduser("~"), "unsaved_export.track")

def load_track_data():
    """Load tracking data from track file"""
    track_file = get_track_file_path()
    if os.path.exists(track_file):
        try:
            with open(track_file, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_track_data(track_data):
    """Save tracking data to track file"""
    track_file = get_track_file_path()
    try:
        os.makedirs(os.path.dirname(track_file), exist_ok=True)
        with open(track_file, 'w') as f:
            json.dump(track_data, f, indent=2)
        return True
    except Exception as e:
        print("Failed to save track file: %s" % str(e))
        return False

def get_final_export_path(base_path, dir_modifier, clean_name, scope, format_type):
    """Get the final export path with directory modifiers applied"""
    extension = get_extension(format_type)
    
    if dir_modifier:
        safe_path = os.path.join(base_path, dir_modifier)
        return os.path.join(safe_path, "%s%s" % (clean_name, extension))
    else:
        return os.path.join(base_path, "%s%s" % (clean_name, extension))

def ensure_directory_exists(filepath):
    """Ensure the directory for a filepath exists, return created status"""
    directory = os.path.dirname(filepath)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)
        return True
    return False

def resolve_export_directory(obj, parent_obj, export_scope, base_export_path):
    """Resolve the export directory based on scope and modifiers"""
    obj_clean, obj_modifiers = parse_modifiers(obj.name)
    
    if export_scope == 'SCENE':
        scene_props = bpy.context.scene.advanced_glb_props
        scene_clean, scene_modifiers = parse_modifiers(scene_props.scene_export_filename)
        dir_path = scene_modifiers.get('dir')
        if dir_path:
            return os.path.join(base_export_path, dir_path)
        return base_export_path
    
    elif export_scope == 'PARENT':
        if parent_obj:
            parent_clean, parent_modifiers = parse_modifiers(parent_obj.name)
            dir_path = parent_modifiers.get('dir')
            if dir_path:
                return os.path.join(base_export_path, dir_path)
        return base_export_path
    
    elif export_scope == 'LAYER':
        # Layers don't have directory modifiers
        return base_export_path
    
    elif export_scope == 'OBJECT':
        if parent_obj:
            parent_clean, parent_modifiers = parse_modifiers(parent_obj.name)
            dir_path = parent_modifiers.get('dir')
            if dir_path:
                return os.path.join(base_export_path, dir_path)
        
        dir_path = obj_modifiers.get('dir')
        if dir_path:
            return os.path.join(base_export_path, dir_path)
        
        return base_export_path
    
    return base_export_path

def move_to_3d_cursor(obj, cursor_location):
    """Move object to 3D cursor while preserving its local transform"""
    world_matrix = obj.matrix_world.copy()
    offset = cursor_location - world_matrix.to_translation()
    obj.matrix_world.translation = world_matrix.translation + offset

def restore_original_position(obj, original_matrix):
    """Restore object to its original position"""
    obj.matrix_world = original_matrix

def safe_apply_modifiers(obj):
    """Safely apply all modifiers to an object, skipping any that fail - 2.79b COMPATIBLE"""
    success_count = 0
    error_count = 0
    
    # Store current selection and active object
    original_active = bpy.context.scene.objects.active
    original_selection = bpy.context.selected_objects
    
    # Use compatibility wrapper for context operations
    with temp_override_compat(object=obj):
        # Use a while loop to safely apply modifiers as the list changes
        while obj.modifiers:
            modifier = obj.modifiers[0]
            modifier_name = modifier.name
            
            try:
                # Select only this object and make it active
                bpy.ops.object.select_all(action='DESELECT')
                obj.select = True
                bpy.context.scene.objects.active = obj
                
                # Apply the modifier
                bpy.ops.object.modifier_apply(modifier=modifier_name)
                success_count += 1
            except RuntimeError as e:
                print("Could not apply modifier '%s' on '%s': %s" % (modifier_name, obj.name, str(e)))
                error_count += 1
                # Remove the problematic modifier or break to avoid infinite loop
                try:
                    obj.modifiers.remove(modifier)
                except:
                    break
    
    # Restore original selection
    bpy.ops.object.select_all(action='DESELECT')
    for obj_orig in original_selection:
        obj_orig.select = True
    bpy.context.scene.objects.active = original_active
    
    return success_count, error_count

def generate_track_file_template():
    """Generate a new tracking file template based on current blend file and settings"""
    try:
        scene_props = bpy.context.scene.advanced_glb_props
        track_data = {}
        
        # Create a basic template structure
        if bpy.data.filepath:
            blend_name = os.path.splitext(os.path.basename(bpy.data.filepath))[0]
        else:
            blend_name = "unsaved"
        
        # Add current export settings to template
        settings_key = "%s|%s|%s" % (scene_props.export_path, scene_props.export_scope, scene_props.export_mode)
        
        track_data[settings_key] = {
            'last_export': {
                'timestamp': datetime.datetime.now().isoformat(),
                'files': [],
                'blend_file': bpy.data.filepath or "unsaved",
                'format': scene_props.export_format,
                'scope': scene_props.export_scope,
                'mode': scene_props.export_mode,
                'export_path': scene_props.export_path,
                'template_generated': True
            },
            'history': []
        }
        
        # Save the template
        if save_track_data(track_data):
            print("Generated new tracking template for: %s" % blend_name)
            return True
        else:
            print("Failed to save tracking template")
            return False
            
    except Exception as e:
        print("Failed to generate tracking template: %s" % str(e))
        return False

def validate_export_modifiers(sk_behavior='BASIC'):
    """
    Validate export modifiers for incompatible combinations, duplicates, and -sk usage
    Returns list of issues with type and message
    """
    issues = []
    
    # Check objects (now representing parent roots)
    for obj in bpy.data.objects:
        clean_name, modifiers = parse_modifiers(obj.name)
        
        # Check for duplicate modifiers
        duplicate_issues = check_duplicate_modifiers(obj.name, clean_name, "Object")
        issues.extend(duplicate_issues)
        
        # BASIC MODE: Only check for incompatible modifiers
        if sk_behavior == 'BASIC':
            # Check for incompatible modifiers
            if modifiers['sk'] and modifiers['dk']:
                issues.append({
                    'type': 'ERROR',
                    'message': "Object '%s': -sk and -dk are incompatible (conflicting exclusion)" % clean_name
                })
        
        # STRICT MODE: Only check -sk usage validation (exclude basic modifier conflicts)
        elif sk_behavior == 'STRICT' and modifiers['sk']:
            # Check if object has children that would be affected
            children = get_object_children(obj)
            if children:
                issues.append({
                    'type': 'WARNING',
                    'message': "Object '%s': -sk used on parent object with %d children (strict mode)" % (clean_name, len(children))
                })
    
    # Check scene filename
    scene_props = bpy.context.scene.advanced_glb_props
    clean_name, modifiers = parse_modifiers(scene_props.scene_export_filename)
    duplicate_issues = check_duplicate_modifiers(scene_props.scene_export_filename, clean_name, "Scene filename")
    issues.extend(duplicate_issues)
    
    return issues

def check_duplicate_modifiers(original_name, clean_name, item_type):
    """
    Check for duplicate modifiers in a name and return issues
    """
    issues = []
    
    # Define modifier patterns
    modifier_patterns = {
        '-dir': r'[\s\-]dir:([^\s]+)',
        '-sep': r'[\s\-]sep',
        '-dk': r'[\s\-]dk',
        '-sk': r'[\s\-]sk',
        '-anim': r'[\s\-]anim'
    }
    
    for modifier, pattern in modifier_patterns.items():
        # Use finditer to get all matches with their positions
        matches = list(re.finditer(pattern, original_name, re.IGNORECASE))
        
        if modifier == '-dir':
            # For -dir, we count the number of occurrences
            count = len(matches)
            if count > 1:
                # Get all directory values found
                dir_values = [match.group(1) for match in matches]
                issues.append({
                    'type': 'ERROR',
                    'message': "%s '%s': %d duplicate -dir modifiers found: %s" % (item_type, clean_name, count, ', '.join(dir_values))
                })
            elif count == 1:
                # Also check if the dir value contains invalid characters
                dir_value = matches[0].group(1)
                if not is_valid_directory_name(dir_value):
                    issues.append({
                        'type': 'ERROR',
                        'message': "%s '%s': -dir value '%s' contains invalid directory characters" % (item_type, clean_name, dir_value)
                    })
        else:
            # For boolean modifiers, count occurrences
            count = len(matches)
            if count > 1:
                issues.append({
                    'type': 'WARNING',
                    'message': "%s '%s': %d duplicate %s modifiers found (redundant)" % (item_type, clean_name, count, modifier)
                })
    
    # Check for conflicting boolean modifiers
    boolean_modifiers = ['-sep', '-dk', '-sk', '-anim']
    modifier_counts = {}
    
    for mod in boolean_modifiers:
        # Count with flexible spacing
        pattern = r'[\s\-]' + mod[1:]  # Remove the '-' from the modifier for pattern
        modifier_counts[mod] = len(re.findall(pattern, original_name, re.IGNORECASE))
    
    # Check for -dk and -sk together (always an error)
    if modifier_counts['-dk'] > 0 and modifier_counts['-sk'] > 0:
        issues.append({
            'type': 'ERROR',
            'message': "%s '%s': -dk and -sk cannot be used together (conflicting exclusion)" % (item_type, clean_name)
        })
    
    return issues

def is_valid_directory_name(dir_name):
    """
    Check if a directory name contains invalid characters
    """
    if not dir_name:
        return False
    
    # Check for invalid characters in directory names
    invalid_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
    
    for char in invalid_chars:
        if char in dir_name:
            return False
    
    # Check for reserved names (Windows)
    reserved_names = ['CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4', 
                     'COM5', 'COM6', 'COM7', 'COM8', 'COM9', 'LPT1', 'LPT2', 
                     'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9']
    
    if dir_name.upper() in reserved_names:
        return False
    
    # Check for leading/trailing spaces or dots
    if dir_name.strip() != dir_name:
        return False
    if dir_name.startswith('.') or dir_name.endswith('.'):
        return False
    
    return True

# ===== MAIN EXPORT FUNCTIONS =====
def export_selected(context, selected_items):
    """Export only selected objects with proper parent hierarchy handling"""
    scene_props = context.scene.advanced_glb_props
    prefs = context.user_preferences.addons[__name__].preferences
    
    if not scene_props.export_path:
        print("Export failed: No export directory specified")
        return {'CANCELLED'}
    
    if not os.path.exists(scene_props.export_path):
        os.makedirs(scene_props.export_path, exist_ok=True)
    
    original_positions = {}
    cursor_location = bpy.context.scene.cursor_location.copy()
    created_directories = set()
    exported_files = []
    
    try:
        # Gather all objects that need to be moved for local origins
        all_export_objects = set()
        
        export_type = scene_props.selected_export_type
        
        if export_type == 'PARENT':
            # Get parent roots from selected objects
            parent_roots = get_selected_parent_roots(selected_items['objects'])
            for parent_obj, objects in parent_roots.items():
                all_export_objects.update(objects)
        else:  # OBJECT
            # Add directly selected objects
            for obj in selected_items['objects']:
                if should_export_object(obj):
                    all_export_objects.add(obj)
        
        # Prevent viewport updates during transformation
        if prefs.export_individual_origins and all_export_objects:
            print("Using local origins - moving selected items to 3D cursor...")
            
            # Store original positions and move to cursor
            for obj in all_export_objects:
                if obj and obj.matrix_world:
                    original_positions[obj] = obj.matrix_world.copy()
                    move_to_3d_cursor(obj, cursor_location)
        
        available_ops = get_available_export_operators()
        print("Available operators: %s" % available_ops)
        success_count = 0
        
        if export_type == 'PARENT':
            # Export selected parent hierarchies as individual files
            parent_roots = get_selected_parent_roots(selected_items['objects'])
            
            for parent_obj, objects in parent_roots.items():
                parent_clean, parent_modifiers = parse_modifiers(parent_obj.name)
                
                # Skip parents with -dk or -sk modifiers
                if parent_modifiers['dk'] or parent_modifiers['sk']:
                    print("Skipping parent '%s' (modifier: -dk or -sk)" % parent_clean)
                    continue
                
                export_path = get_final_export_path(scene_props.export_path, parent_modifiers.get('dir'), parent_clean, 'PARENT', scene_props.export_format)
                
                if ensure_directory_exists(export_path):
                    dir_created = os.path.dirname(export_path)
                    if dir_created not in created_directories:
                        print("Created directory: %s" % dir_created)
                        created_directories.add(dir_created)
                
                bpy.ops.object.select_all(action='DESELECT')
                object_count = 0
                
                # Select all objects in this parent hierarchy
                for obj in objects:
                    if should_export_object(obj):
                        obj.select = True
                        object_count += 1
                
                if object_count == 0:
                    print("Skipping '%s': No exportable objects" % parent_clean)
                    continue
                
                try:
                    # Apply modifiers if enabled
                    if prefs.apply_modifiers:
                        for obj in objects:
                            if should_export_object(obj):
                                success, errors = safe_apply_modifiers(obj)
                                if success > 0:
                                    print("Applied %d modifiers to '%s'" % (success, obj.name))
                                if errors > 0:
                                    print("Failed to apply %d modifiers to '%s'" % (errors, obj.name))
                    
                    if scene_props.export_format == 'OBJ':
                        success = export_obj_compat(
                            filepath=export_path,
                            use_selection=True,
                            apply_modifiers=False  # Already applied above if needed
                        )
                        if not success:
                            continue
                    elif scene_props.export_format == 'FBX':
                        # FBX export
                        export_params = {
                            'filepath': export_path,
                            'use_selection': True,
                            'use_mesh_modifiers': False,  # Already applied above if needed
                            'bake_anim': scene_props.apply_animations,
                            'axis_forward': 'Y',
                            'axis_up': 'Z' if scene_props.export_up_axis == 'Z' else 'Y'
                        }
                        
                        bpy.ops.export_scene.fbx(**export_params)
                    elif scene_props.export_format == 'STL':
                        # STL export
                        export_params = {
                            'filepath': export_path,
                            'use_selection': True,
                            'use_mesh_modifiers': False,
                            'global_scale': 1.0,
                            'use_scene_unit': False,
                            'ascii': False,
                            'use_mesh_modifiers': False
                        }
                        bpy.ops.export_mesh.stl(**export_params)
                    elif scene_props.export_format == 'PLY':
                        # PLY export
                        export_params = {
                            'filepath': export_path,
                            'use_selection': True,
                            'use_mesh_modifiers': False,
                            'use_normals': True,
                            'use_uv_coords': True,
                            'use_colors': True,
                            'global_scale': 1.0
                        }
                        bpy.ops.export_mesh.ply(**export_params)
                    elif scene_props.export_format == 'DAE':
                        # Collada DAE export
                        export_params = {
                            'filepath': export_path,
                            'use_selection': True,
                            'use_mesh_modifiers': False,
                            'apply_modifiers': False,
                            'use_export_pref': True
                        }
                        bpy.ops.wm.collada_export(**export_params)
                    elif scene_props.export_format == 'X3D':
                        # X3D export
                        export_params = {
                            'filepath': export_path,
                            'use_selection': True,
                            'use_mesh_modifiers': False
                        }
                        bpy.ops.export_scene.x3d(**export_params)
                    
                    print("Exported selected parent '%s' to: %s" % (parent_clean, export_path))
                    success_count += 1
                    exported_files.append(export_path)
                except Exception as e:
                    print("Parent export failed for '%s': %s" % (parent_clean, str(e)))
        
        else:  # OBJECT export type
            # Export selected objects as individual files
            for obj in selected_items['objects']:
                if not should_export_object(obj):
                    continue
                
                # Skip if object was already exported as part of a parent hierarchy
                if export_type == 'PARENT' and any(
                    obj in objects for objects in parent_roots.values()
                ):
                    print("Skipping '%s' (already exported via parent)" % obj.name)
                    continue
                
                obj_clean, obj_modifiers = parse_modifiers(obj.name)
                export_dir = resolve_export_directory(obj, obj.parent, 'OBJECT', scene_props.export_path)
                export_path = os.path.join(export_dir, "%s%s" % (obj_clean, get_extension(scene_props.export_format)))
                
                if ensure_directory_exists(export_path):
                    dir_created = os.path.dirname(export_path)
                    if dir_created not in created_directories:
                        print("Created directory: %s" % dir_created)
                        created_directories.add(dir_created)
                
                bpy.ops.object.select_all(action='DESELECT')
                obj.select = True
                
                try:
                    # Apply modifiers if enabled
                    if prefs.apply_modifiers:
                        success, errors = safe_apply_modifiers(obj)
                        if success > 0:
                            print("Applied %d modifiers to '%s'" % (success, obj.name))
                        if errors > 0:
                            print("Failed to apply %d modifiers to '%s'" % (errors, obj.name))
                    
                    if scene_props.export_format == 'OBJ':
                        success = export_obj_compat(
                            filepath=export_path,
                            use_selection=True,
                            apply_modifiers=False
                        )
                        if not success:
                            continue
                    elif scene_props.export_format == 'FBX':
                        export_params = {
                            'filepath': export_path,
                            'use_selection': True,
                            'use_mesh_modifiers': False,
                            'bake_anim': scene_props.apply_animations,
                            'axis_forward': 'Y',
                            'axis_up': 'Z' if scene_props.export_up_axis == 'Z' else 'Y'
                        }
                        
                        bpy.ops.export_scene.fbx(**export_params)
                    elif scene_props.export_format == 'STL':
                        export_params = {
                            'filepath': export_path,
                            'use_selection': True,
                            'use_mesh_modifiers': False,
                            'global_scale': 1.0,
                            'use_scene_unit': False,
                            'ascii': False,
                            'use_mesh_modifiers': False
                        }
                        bpy.ops.export_mesh.stl(**export_params)
                    elif scene_props.export_format == 'PLY':
                        export_params = {
                            'filepath': export_path,
                            'use_selection': True,
                            'use_mesh_modifiers': False,
                            'use_normals': True,
                            'use_uv_coords': True,
                            'use_colors': True,
                            'global_scale': 1.0
                        }
                        bpy.ops.export_mesh.ply(**export_params)
                    elif scene_props.export_format == 'DAE':
                        export_params = {
                            'filepath': export_path,
                            'use_selection': True,
                            'use_mesh_modifiers': False,
                            'apply_modifiers': False,
                            'use_export_pref': True
                        }
                        bpy.ops.wm.collada_export(**export_params)
                    elif scene_props.export_format == 'X3D':
                        export_params = {
                            'filepath': export_path,
                            'use_selection': True,
                            'use_mesh_modifiers': False
                        }
                        bpy.ops.export_scene.x3d(**export_params)
                    
                    print("Exported selected object '%s' to: %s" % (obj_clean, export_path))
                    success_count += 1
                    exported_files.append(export_path)
                except Exception as e:
                    print("Object export failed for '%s': %s" % (obj_clean, str(e)))
        
        return {'FINISHED'} if success_count > 0 else {'CANCELLED'}
    
    finally:
        if exported_files and prefs.enable_export_tracking:
            update_track_file(exported_files, scene_props.export_path)
            print("Tracking updated: %d files recorded" % len(exported_files))
        
        if original_positions:
            print("Restoring original object positions...")
            for obj, original_matrix in original_positions.items():
                if obj:
                    obj.matrix_world = original_matrix

def export_main(context):
    """Main export function for 2.79b"""
    scene_props = context.scene.advanced_glb_props
    prefs = context.user_preferences.addons[__name__].preferences
    
    if not scene_props.export_path:
        print("Export failed: No export directory specified")
        return {'CANCELLED'}
    
    if not os.path.exists(scene_props.export_path):
        os.makedirs(scene_props.export_path, exist_ok=True)
    
    original_positions = {}
    cursor_location = bpy.context.scene.cursor_location.copy()
    created_directories = set()
    exported_files = []
    
    try:
        # Prevent viewport updates during transformation
        if prefs.export_individual_origins and scene_props.export_scope != 'SCENE':
            print("Using local origins - moving to 3D cursor...")
            
            if scene_props.export_scope == 'PARENT':
                parent_roots = find_parent_export_roots()
                for parent_obj, objects in parent_roots.items():
                    if objects:
                        parent_positions = move_parent_to_origin(objects, cursor_location)
                        original_positions.update(parent_positions)
            
            elif scene_props.export_scope == 'LAYER':
                export_layers = find_all_layers_with_objects()
                for layer_index, objects in export_layers.items():
                    for obj in objects:
                        original_positions[obj] = obj.matrix_world.copy()
                        move_to_3d_cursor(obj, cursor_location)
            
            elif scene_props.export_scope == 'OBJECT':
                for obj in bpy.data.objects:
                    if should_export_object(obj):
                        original_positions[obj] = obj.matrix_world.copy()
                        move_to_3d_cursor(obj, cursor_location)
        
        available_ops = get_available_export_operators()
        print("Available operators: %s" % available_ops)
        
        if scene_props.export_scope == 'SCENE':
            scene_clean, scene_modifiers = parse_modifiers(scene_props.scene_export_filename)
            export_path = get_final_export_path(scene_props.export_path, scene_modifiers.get('dir'), scene_clean, 'SCENE', scene_props.export_format)
            
            if ensure_directory_exists(export_path):
                print("Created directory: %s" % os.path.dirname(export_path))
            
            try:
                if scene_props.export_format == 'OBJ':
                    success = export_obj_compat(
                        filepath=export_path,
                        use_selection=False,
                        apply_modifiers=prefs.apply_modifiers
                    )
                    if not success:
                        return {'CANCELLED'}
                elif scene_props.export_format == 'FBX':
                    export_params = {
                        'filepath': export_path,
                        'use_selection': False,
                        'use_mesh_modifiers': prefs.apply_modifiers,
                        'bake_anim': scene_props.apply_animations,
                        'axis_forward': 'Y',
                        'axis_up': 'Z' if scene_props.export_up_axis == 'Z' else 'Y'
                    }
                    
                    bpy.ops.export_scene.fbx(**export_params)
                elif scene_props.export_format == 'STL':
                    export_params = {
                        'filepath': export_path,
                        'use_selection': False,
                        'use_mesh_modifiers': prefs.apply_modifiers,
                        'global_scale': 1.0,
                        'use_scene_unit': False,
                        'ascii': False,
                        'use_mesh_modifiers': prefs.apply_modifiers
                    }
                    bpy.ops.export_mesh.stl(**export_params)
                elif scene_props.export_format == 'PLY':
                    export_params = {
                        'filepath': export_path,
                        'use_selection': False,
                        'use_mesh_modifiers': prefs.apply_modifiers,
                        'use_normals': True,
                        'use_uv_coords': True,
                        'use_colors': True,
                        'global_scale': 1.0
                    }
                    bpy.ops.export_mesh.ply(**export_params)
                elif scene_props.export_format == 'DAE':
                    export_params = {
                        'filepath': export_path,
                        'use_selection': False,
                        'use_mesh_modifiers': prefs.apply_modifiers,
                        'apply_modifiers': prefs.apply_modifiers,
                        'use_export_pref': True
                    }
                    bpy.ops.wm.collada_export(**export_params)
                elif scene_props.export_format == 'X3D':
                    export_params = {
                        'filepath': export_path,
                        'use_selection': False,
                        'use_mesh_modifiers': prefs.apply_modifiers
                    }
                    bpy.ops.export_scene.x3d(**export_params)
                
                print("Exported scene to: %s" % export_path)
                exported_files.append(export_path)
                return {'FINISHED'}
            except Exception as e:
                print("Scene export failed: %s" % str(e))
                return {'CANCELLED'}
        
        elif scene_props.export_scope == 'PARENT':
            parent_roots = find_parent_export_roots()
            success_count = 0
            
            for parent_obj, objects in parent_roots.items():
                parent_clean, parent_modifiers = parse_modifiers(parent_obj.name)
                export_path = get_final_export_path(scene_props.export_path, parent_modifiers.get('dir'), parent_clean, 'PARENT', scene_props.export_format)
                
                if ensure_directory_exists(export_path):
                    dir_created = os.path.dirname(export_path)
                    if dir_created not in created_directories:
                        print("Created directory: %s" % dir_created)
                        created_directories.add(dir_created)
                
                bpy.ops.object.select_all(action='DESELECT')
                object_count = 0
                
                for obj in objects:
                    obj.select = True
                    object_count += 1
                
                if object_count == 0:
                    print("Skipping '%s': No exportable objects" % parent_clean)
                    continue
                
                try:
                    if scene_props.export_format == 'OBJ':
                        success = export_obj_compat(
                            filepath=export_path,
                            use_selection=True,
                            apply_modifiers=prefs.apply_modifiers
                        )
                        if not success:
                            continue
                    elif scene_props.export_format == 'FBX':
                        export_params = {
                            'filepath': export_path,
                            'use_selection': True,
                            'use_mesh_modifiers': prefs.apply_modifiers,
                            'bake_anim': scene_props.apply_animations,
                            'axis_forward': 'Y',
                            'axis_up': 'Z' if scene_props.export_up_axis == 'Z' else 'Y'
                        }
                        
                        bpy.ops.export_scene.fbx(**export_params)
                    elif scene_props.export_format == 'STL':
                        export_params = {
                            'filepath': export_path,
                            'use_selection': True,
                            'use_mesh_modifiers': prefs.apply_modifiers,
                            'global_scale': 1.0,
                            'use_scene_unit': False,
                            'ascii': False,
                            'use_mesh_modifiers': prefs.apply_modifiers
                        }
                        bpy.ops.export_mesh.stl(**export_params)
                    elif scene_props.export_format == 'PLY':
                        export_params = {
                            'filepath': export_path,
                            'use_selection': True,
                            'use_mesh_modifiers': prefs.apply_modifiers,
                            'use_normals': True,
                            'use_uv_coords': True,
                            'use_colors': True,
                            'global_scale': 1.0
                        }
                        bpy.ops.export_mesh.ply(**export_params)
                    elif scene_props.export_format == 'DAE':
                        export_params = {
                            'filepath': export_path,
                            'use_selection': True,
                            'use_mesh_modifiers': prefs.apply_modifiers,
                            'apply_modifiers': prefs.apply_modifiers,
                            'use_export_pref': True
                        }
                        bpy.ops.wm.collada_export(**export_params)
                    elif scene_props.export_format == 'X3D':
                        export_params = {
                            'filepath': export_path,
                            'use_selection': True,
                            'use_mesh_modifiers': prefs.apply_modifiers
                        }
                        bpy.ops.export_scene.x3d(**export_params)
                    
                    print("Exported '%s' to: %s" % (parent_clean, export_path))
                    success_count += 1
                    
                    exported_files.append(export_path)
                except Exception as e:
                    print("Parent export failed for '%s': %s" % (parent_clean, str(e)))
            
            return {'FINISHED'} if success_count > 0 else {'CANCELLED'}
        
        elif scene_props.export_scope == 'LAYER':
            # Use ALL layers, not just active ones
            export_layers = find_all_layers_with_objects()
            success_count = 0
            
            for layer_index, objects in export_layers.items():
                layer_name = "layer_%d" % (layer_index + 1)
                export_path = os.path.join(scene_props.export_path, "%s%s" % (layer_name, get_extension(scene_props.export_format)))
                
                if ensure_directory_exists(export_path):
                    dir_created = os.path.dirname(export_path)
                    if dir_created not in created_directories:
                        print("Created directory: %s" % dir_created)
                        created_directories.add(dir_created)
                
                bpy.ops.object.select_all(action='DESELECT')
                object_count = 0
                
                for obj in objects:
                    obj.select = True
                    object_count += 1
                
                if object_count == 0:
                    print("Skipping layer %d: No exportable objects" % (layer_index + 1))
                    continue
                
                try:
                    if scene_props.export_format == 'OBJ':
                        success = export_obj_compat(
                            filepath=export_path,
                            use_selection=True,
                            apply_modifiers=prefs.apply_modifiers
                        )
                        if not success:
                            continue
                    elif scene_props.export_format == 'FBX':
                        export_params = {
                            'filepath': export_path,
                            'use_selection': True,
                            'use_mesh_modifiers': prefs.apply_modifiers,
                            'bake_anim': scene_props.apply_animations,
                            'axis_forward': 'Y',
                            'axis_up': 'Z' if scene_props.export_up_axis == 'Z' else 'Y'
                        }
                        
                        bpy.ops.export_scene.fbx(**export_params)
                    elif scene_props.export_format == 'STL':
                        export_params = {
                            'filepath': export_path,
                            'use_selection': True,
                            'use_mesh_modifiers': prefs.apply_modifiers,
                            'global_scale': 1.0,
                            'use_scene_unit': False,
                            'ascii': False,
                            'use_mesh_modifiers': prefs.apply_modifiers
                        }
                        bpy.ops.export_mesh.stl(**export_params)
                    elif scene_props.export_format == 'PLY':
                        export_params = {
                            'filepath': export_path,
                            'use_selection': True,
                            'use_mesh_modifiers': prefs.apply_modifiers,
                            'use_normals': True,
                            'use_uv_coords': True,
                            'use_colors': True,
                            'global_scale': 1.0
                        }
                        bpy.ops.export_mesh.ply(**export_params)
                    elif scene_props.export_format == 'DAE':
                        export_params = {
                            'filepath': export_path,
                            'use_selection': True,
                            'use_mesh_modifiers': prefs.apply_modifiers,
                            'apply_modifiers': prefs.apply_modifiers,
                            'use_export_pref': True
                        }
                        bpy.ops.wm.collada_export(**export_params)
                    elif scene_props.export_format == 'X3D':
                        export_params = {
                            'filepath': export_path,
                            'use_selection': True,
                            'use_mesh_modifiers': prefs.apply_modifiers
                        }
                        bpy.ops.export_scene.x3d(**export_params)
                    
                    print("Exported layer %d to: %s" % (layer_index + 1, export_path))
                    success_count += 1
                    exported_files.append(export_path)
                except Exception as e:
                    print("Layer export failed for layer %d: %s" % (layer_index + 1, str(e)))
            
            return {'FINISHED'} if success_count > 0 else {'CANCELLED'}
        
        elif scene_props.export_scope == 'OBJECT':
            success_count = 0
            
            for obj in bpy.data.objects:
                if not should_export_object(obj):
                    continue
                
                obj_clean, obj_modifiers = parse_modifiers(obj.name)
                export_dir = resolve_export_directory(obj, obj.parent, 'OBJECT', scene_props.export_path)
                export_path = os.path.join(export_dir, "%s%s" % (obj_clean, get_extension(scene_props.export_format)))
                
                if ensure_directory_exists(export_path):
                    dir_created = os.path.dirname(export_path)
                    if dir_created not in created_directories:
                        print("Created directory: %s" % dir_created)
                        created_directories.add(dir_created)
                
                bpy.ops.object.select_all(action='DESELECT')
                obj.select = True
                
                try:
                    if scene_props.export_format == 'OBJ':
                        success = export_obj_compat(
                            filepath=export_path,
                            use_selection=True,
                            apply_modifiers=prefs.apply_modifiers
                        )
                        if not success:
                            continue
                    elif scene_props.export_format == 'FBX':
                        export_params = {
                            'filepath': export_path,
                            'use_selection': True,
                            'use_mesh_modifiers': prefs.apply_modifiers,
                            'bake_anim': scene_props.apply_animations,
                            'axis_forward': 'Y',
                            'axis_up': 'Z' if scene_props.export_up_axis == 'Z' else 'Y'
                        }
                        
                        bpy.ops.export_scene.fbx(**export_params)
                    elif scene_props.export_format == 'STL':
                        export_params = {
                            'filepath': export_path,
                            'use_selection': True,
                            'use_mesh_modifiers': prefs.apply_modifiers,
                            'global_scale': 1.0,
                            'use_scene_unit': False,
                            'ascii': False,
                            'use_mesh_modifiers': prefs.apply_modifiers
                        }
                        bpy.ops.export_mesh.stl(**export_params)
                    elif scene_props.export_format == 'PLY':
                        export_params = {
                            'filepath': export_path,
                            'use_selection': True,
                            'use_mesh_modifiers': prefs.apply_modifiers,
                            'use_normals': True,
                            'use_uv_coords': True,
                            'use_colors': True,
                            'global_scale': 1.0
                        }
                        bpy.ops.export_mesh.ply(**export_params)
                    elif scene_props.export_format == 'DAE':
                        export_params = {
                            'filepath': export_path,
                            'use_selection': True,
                            'use_mesh_modifiers': prefs.apply_modifiers,
                            'apply_modifiers': prefs.apply_modifiers,
                            'use_export_pref': True
                        }
                        bpy.ops.wm.collada_export(**export_params)
                    elif scene_props.export_format == 'X3D':
                        export_params = {
                            'filepath': export_path,
                            'use_selection': True,
                            'use_mesh_modifiers': prefs.apply_modifiers
                        }
                        bpy.ops.export_scene.x3d(**export_params)
                    
                    print("Exported '%s' to: %s" % (obj_clean, export_path))
                    success_count += 1
                    exported_files.append(export_path)
                except Exception as e:
                    print("Object export failed for '%s': %s" % (obj_clean, str(e)))
            
            return {'FINISHED'} if success_count > 0 else {'CANCELLED'}
        
        return {'CANCELLED'}
    
    finally:
        if exported_files and prefs.enable_export_tracking:
            update_track_file(exported_files, scene_props.export_path)
            print("Tracking updated: %d files recorded" % len(exported_files))
        
        if original_positions:
            print("Restoring original object positions...")
            for obj, original_matrix in original_positions.items():
                if obj:
                    obj.matrix_world = original_matrix

@persistent
def on_save_handler(dummy):
    if not bpy.context.user_preferences.addons.get(__name__):
        return
    
    scene_props = bpy.context.scene.advanced_glb_props
    if not scene_props.auto_export_on_save:
        return
    
    if not scene_props.export_path:
        print("Auto-export skipped: Export directory not configured")
        return
    
    export_main(bpy.context)

def register():
    bpy.utils.register_class(ADVANCED_GLB_OT_export)
    bpy.utils.register_class(ADVANCED_GLB_OT_export_selected)
    bpy.utils.register_class(ADVANCED_GLB_OT_highlight_exportable)
    bpy.utils.register_class(ADVANCED_GLB_OT_delete_track_file)
    bpy.utils.register_class(ADVANCED_GLB_OT_execute_order_66)
    bpy.utils.register_class(ADVANCED_GLB_OT_show_validation_report)
    bpy.utils.register_class(ADVANCED_GLB_OT_validate_export_modifiers)
    bpy.utils.register_class(ADVANCED_GLB_PT_panel)
    bpy.utils.register_class(AdvancedGLBPreferences)
    bpy.utils.register_class(AdvancedGLBSceneProperties)
    
    bpy.types.Scene.advanced_glb_props = bpy.props.PointerProperty(type=AdvancedGLBSceneProperties)
    
    if on_save_handler not in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.append(on_save_handler)

def unregister():
    # Clean up any running exports
    ExportState.is_exporting = False
    
    bpy.utils.unregister_class(ADVANCED_GLB_OT_export)
    bpy.utils.unregister_class(ADVANCED_GLB_OT_export_selected)
    bpy.utils.unregister_class(ADVANCED_GLB_OT_highlight_exportable)
    bpy.utils.unregister_class(ADVANCED_GLB_OT_delete_track_file)
    bpy.utils.unregister_class(ADVANCED_GLB_OT_execute_order_66)
    bpy.utils.unregister_class(ADVANCED_GLB_OT_show_validation_report)
    bpy.utils.unregister_class(ADVANCED_GLB_OT_validate_export_modifiers)
    bpy.utils.unregister_class(ADVANCED_GLB_PT_panel)
    bpy.utils.unregister_class(AdvancedGLBPreferences)
    bpy.utils.unregister_class(AdvancedGLBSceneProperties)
    
    del bpy.types.Scene.advanced_glb_props
    
    if on_save_handler in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.remove(on_save_handler)

if __name__ == "__main__":
    register()
