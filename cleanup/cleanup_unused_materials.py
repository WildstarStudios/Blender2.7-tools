# -*- coding: utf-8 -*-
bl_info = {
    "name": "Material Cleanup",
    "author": "Sirsloth2008",
    "version": (1, 0),
    "blender": (2, 79, 0),
    "location": "File > Clean Up",
    "description": "Removes unused materials from the blend file",
    "warning": "",
    "category": "System"
}

import bpy

class CleanUnusedMaterialsOperator(bpy.types.Operator):
    """Delete all unused materials from the blend file"""
    bl_idname = "file.clean_unused_materials"
    bl_label = "Clean Unused Materials"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        initial_count = len(bpy.data.materials)
        removed_count = 0
        
        # Create a static copy for safe iteration
        materials = list(bpy.data.materials)
        
        for material in materials:
            # Skip protected materials
            if material.use_fake_user:
                continue
                
            # Check all possible users (objects, particle systems, etc.)
            if material.users == 0:
                # Special case: Skip the default material only if it's the only material
                if material.name == "Material" and initial_count == 1:
                    self.report({'INFO'}, "Default material preserved as fallback")
                    continue
                    
                try:
                    bpy.data.materials.remove(material)
                    removed_count += 1
                except:
                    pass  # Skip if any error occurs

        self.report({'INFO'}, "Removed {} unused materials. {} remain.".format(
            removed_count, 
            initial_count - removed_count
        ))
        return {'FINISHED'}

# New submenu class
class CleanUpMenu(bpy.types.Menu):
    bl_label = "Clean Up"
    bl_idname = "INFO_MT_file_cleanup"

    def draw(self, context):
        self.layout.operator(CleanUnusedMaterialsOperator.bl_idname, 
                             icon='MATERIAL_DATA',
                             text="Clean Unused Materials")

# Add to File menu
def menu_func(self, context):
    self.layout.separator()
    self.layout.menu(CleanUpMenu.bl_idname, icon='BRUSH_DATA')

def register():
    bpy.utils.register_class(CleanUnusedMaterialsOperator)
    bpy.utils.register_class(CleanUpMenu)
    bpy.types.INFO_MT_file.append(menu_func)

def unregister():
    bpy.utils.unregister_class(CleanUnusedMaterialsOperator)
    bpy.utils.unregister_class(CleanUpMenu)
    bpy.types.INFO_MT_file.remove(menu_func)

if __name__ == "__main__":
    register()
