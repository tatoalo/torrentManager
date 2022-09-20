# Releasing

1. Update the `CHANGELOG.md`:

2. Commit

   ```
   $ git commit -am "Prepare version X.Y.X"
   ```

3. Tag

   ```
   $ git tag -am "Version X.Y.Z" X.Y.Z
   ```

4. Push!

   ```
   $ git push && git push --tags
   ```