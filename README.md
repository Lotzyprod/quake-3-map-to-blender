Features:

- Import BSP files to view your map in blender (many shader functions are supported. even animations like tcmap scroll)
- Bake lightmaps in blender / Edit lightmap coordinates
- Bake lightgrid
- Bake vertex colors
- Edit texture coordinates
- Edit normals
- Edit entities

(all edits can be patched back into the BSP)

- Import MD3 files
- Export MD3 files with custom normals (e.g. for smooth shading. see attached video and more about MD3 models)

How to install:

- Download the addon zip file (see attachments below)
- Open Blender
- Go to 'edit -> preferences -> Add-ons'
- Click the 'Install...' button on the top right and navigate to the zip you downloaded, then click 'Install Add-on'
- Tick the checkbox next to 'Import-Export: Import id Tech 3 BSP' to enable the addon
- Expand the entry next to 'basepath' navigate to your 'quake3/baseq3' directory. Note that the addon can not read pk3 files, so you have to extract the pak files in order for the addon to be able to read the default textures and shaders. Also extract contents from any pk3 files you want to load. (If you want to keep your game directory clean, you can also create a separate directory for the addon to read from)