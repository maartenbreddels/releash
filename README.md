# What?
 * releash is a command line tools to automate version bumping, and releasing software. 
 * Works with monorepos (multiple projects in 1 repo)
 * No config files, config script (.releash.py)
 * Supports conda-forge (making pull requests and updating recipes)
 * It can bump version numbers in python file, c header files using semantic versioning, e.g. `releash bump`:
     ```bash
     $ releash bump`
     version was 0.1.5, is now 0.1.6
     wrote to releash.py
     git commit -m "Release 0.1.6" releash.py
     [master eb64d30] Release 0.1.6
      1 file changed, 2 insertions(+), 2 deletions(-)
     ```
  * Release to pypi, e.g. `releash release`
    ```bash
    $ releash release
    cd . && python setup.py sdist upload
    running sdist
    running egg_info
    writing entry points to releash.egg-info/entry_points.txt
    writing dependency_links to releash.egg-info/dependency_links.txt
    .....
    Submitting dist/releash-0.1.6.tar.gz to https://upload.pypi.org/legacy/
    Server response (200): OK
    git tag -a v0.1.6 -m "Release 0.1.6"
    git push   && git push  --tags
    Counting objects: 21, done.
    Delta compression using up to 4 threads.
    Compressing objects: 100% (21/21), done.
    Writing objects: 100% (21/21), 2.49 KiB | 0 bytes/s, done.
    Total 21 (delta 14), reused 0 (delta 0)
    remote: Resolving deltas: 100% (14/14), completed with 2 local objects.
    To git@github.com:maartenbreddels/releash.git
       3e74513..eb64d30  master -> master
    Counting objects: 1, done.
    Writing objects: 100% (1/1), 163 bytes | 0 bytes/s, done.
    Total 1 (delta 0), reused 0 (delta 0)
    To git@github.com:maartenbreddels/releash.git
     * [new tag]         v0.1.6 -> v0.1.6
    ```
