# Project storage

Developer contract; user-facing instructions are consolidated in [the user guide](user/README.md).

The second page requires confirmation of the save location and project name. The save location is prefilled from the settings service, defaulting to the resolved Yaki project's `output` directory.
Start creates that project directly in the selected parent directory. Existing
destinations, invalid names, unwritable parents and legacy cache overlap are rejected.
The location and name are fixed once started. New jobs need no second copy or
publication step, and opening the project folder never creates a cache folder.

## Layout and recovery

The final video appears at the project root only after style confirmation and
successful export. Source media, intermediate results and logs stay under
`intermediates`. Export retains the existing pending-file and atomic completion
behavior. Closing the launcher leaves its detached worker running.

Direct projects keep destination metadata and control state in
`intermediates/destination.local.json` and `intermediates/control.local.json`.
Lifecycle locks prevent concurrent workers and edits. Internal output references
remain relative; a local source reference may contain its original absolute path.
The ignored `.local/projects.json` index records project locations on this machine.
It is not a default destination or a portable project registry. Moving a project
manually does not automatically update that index.

Reopen the same source and select its pending project to resume. Completed
preparation is reused; subtitle styling still precedes final export. There is
no cloud processing merely from selecting or previewing a source.

## Legacy jobs

Existing sibling `RinaYakiCache` jobs retain verified copy/publication and retry
support. Their destination may still be changed before publication. A failed
copy preserves the cache; successful verification precedes cleanup. New direct
projects never use this migration path. Existing videos are not moved or deleted.

Regression coverage includes direct export without publication, legacy migration,
active-worker exclusion, UI navigation, and detached export. No paid API calls
are required for these tests.
