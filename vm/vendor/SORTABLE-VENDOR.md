# Sortable vendored file

**Version:** 1.15.7
**License:** MIT
**Source:** https://github.com/SortableJS/Sortable

Version marker is visible in the header comment of `sortable.min.js`:

```
/*! Sortable 1.15.7 - MIT | git://github.com/SortableJS/Sortable.git */
```

## Updating

```bash
VERSION=1.15.7
curl -sL "https://cdn.jsdelivr.net/npm/sortablejs@${VERSION}/Sortable.min.js" \
  -o vm/vendor/sortable.min.js
```

Check the `/*! Sortable X.Y.Z ... */` header in the downloaded file to
confirm the version, then update the number at the top of this doc.
