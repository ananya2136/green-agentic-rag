# GitHub Authentication Fix

## Problem
You're logged in as `ananya2136` but trying to push to `ananya-github16`'s repository.

## Solution Options

### Option 1: Use Your Own Repository (Recommended)
Create a repository under your account (`ananya2136`):

1. Go to https://github.com/new
2. Name: `green-agentic-rag`
3. Make it **Public**
4. Don't initialize with anything
5. Create repository

Then update the remote:
```bash
git remote remove origin
git remote add origin https://github.com/ananya2136/green-agentic-rag
git push -u origin main
```

### Option 2: Get Access to ananya-github16's Repository
If `ananya-github16` is your other account, you need to:

1. **Switch GitHub accounts** in your browser/git credentials
2. **Or** use a Personal Access Token from `ananya-github16`:
   ```bash
   git push https://<TOKEN>@github.com/ananya-github16/green-agentic-rag-2.0 main
   ```

### Option 3: Fork the Repository
If you don't own `ananya-github16`, you can't push to it directly.

## Quick Command
I've already removed the old remote. Now run:

```bash
# If using your own account (ananya2136):
git remote add origin https://github.com/ananya2136/green-agentic-rag
git push -u origin main

# Or if you have access to ananya-github16 and created the -2.0 repo:
git push -u origin main
```

After successful push, we'll deploy to Render!
