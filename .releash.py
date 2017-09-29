from releash import *
myself = add_package(".", "releash")
myself.version_source = VersionSource(myself, 'releash.py')
myself.version_targets.append(VersionTargetGitTag(myself))
myself.version_targets.append(VersionTarget(myself, 'releash.py'))
myself.release_targets.append(ReleaseTargetSourceDist(myself))
myself.release_targets.append(ReleaseTargetGitPush(myself))
myself.release_targets.append(ReleaseTargetCondaForge(myself, 'releash-fake-feedstock'))
