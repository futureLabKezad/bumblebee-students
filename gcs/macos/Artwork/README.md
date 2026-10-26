# Artwork

Icon files that are not app resources, so SwiftPM does not copy them into the
`GCSApp_GCSApp.bundle` of every build:

- `AppIcon.icns`: the Finder / Dock icon. `build_app.sh` puts it into
  `Contents/Resources/` (named in `Info.plist` as `CFBundleIconFile`).
- `AppIcon-original.png`: the full-size source of the icon.

The app itself shows `Sources/GCSApp/Resources/AppIcon.png` (`AppIcon.image` in `AppMain.swift`).
