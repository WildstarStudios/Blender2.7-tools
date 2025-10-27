# A custom object to use with the old parent system of 2.79 to try to replicate the new collection system.
# Cgroup stands for Collection Group
bl_info = {
    "name": "Cgroup Object",
    "author": "WildstarStudios",
    "version": (1, 0),
    "blender": (2, 79, 0),
    "location": "View3D > Add > Empty",
    "description": "Adds a Cgroup object for parenting",
    "category": "Add Empty",
}

import bpy
from bpy.types import Operator
from bpy_extras.object_utils import AddObjectHelper


class OBJECT_OT_add_cgroup(Operator, AddObjectHelper):
    """Create a new Cgroup object"""
    bl_idname = "object.add_cgroup"
    bl_label = "Cgroup"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # Create empty object
        bpy.ops.object.empty_add(type='PLAIN_AXES')
        obj = context.active_object
        obj.name = "Cgroup"
        
        # Add custom property
        obj["is_cgroup"] = True
        
        return {'FINISHED'}


def add_cgroup_button(self, context):
    self.layout.operator(
        OBJECT_OT_add_cgroup.bl_idname,
        text="Cgroup",
        icon='GROUP'
    )


def register():
    bpy.utils.register_class(OBJECT_OT_add_cgroup)
    bpy.types.INFO_MT_add.append(add_cgroup_button)


def unregister():
    bpy.utils.unregister_class(OBJECT_OT_add_cgroup)
    bpy.types.INFO_MT_add.remove(add_cgroup_button)


if __name__ == "__main__":
    register()
