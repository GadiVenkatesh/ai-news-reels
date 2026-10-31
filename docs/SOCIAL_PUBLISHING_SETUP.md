# Social publishing setup

The Generate AI News Reel workflow produces the fixed 60-second, 1080x1920 MP4. The separate Publish AI News Reel workflow downloads that artifact and publishes it.

## How it works

1. Generate AI News Reel completes successfully.
2. Publish AI News Reel downloads the generated MP4 and adjacent JSON metadata.
3. `app/publish.py` prepares platform-specific title, description, source attribution and hashtags.
4. YouTube Data API uploads the local MP4 using OAuth 2.0 refresh-token credentials.
5. Instagram publishing creates a resumable Reel container, uploads the MP4 bytes directly to Meta's `rupload.facebook.com` endpoint, waits for processing, then calls `media_publish`.
6. The workflow saves `publishing-report.json` as an Actions artifact.

**No AWS account, S3 bucket, AWS credentials, AWS Region, or temporary public video hosting is used.**

## Required GitHub repository secrets

### YouTube

- `YOUTUBE_CLIENT_ID`
- `YOUTUBE_CLIENT_SECRET`
- `YOUTUBE_REFRESH_TOKEN`

Enable YouTube Data API v3 in a Google Cloud project, configure an OAuth consent screen, create an OAuth client, and authorize the YouTube channel with the `youtube.upload` scope. Store the resulting refresh token as a GitHub Actions secret. Never commit tokens or client secrets.

### Instagram

- `INSTAGRAM_USER_ID`
- `INSTAGRAM_ACCESS_TOKEN`

Set the repository variable `META_GRAPH_API_VERSION` to a currently supported version used by your Meta app.

**Important API requirement:** this direct/resumable video upload flow is documented for Meta apps using **Facebook Login for Business**. Your Instagram professional account (Business or Creator) must have publishing access and the relevant Meta app permissions. If your app uses Instagram Login instead, verify its supported publishing flow before using this direct upload implementation.

## Optional GitHub repository variables

- `YOUTUBE_PRIVACY_STATUS`: defaults to `private` for safer initial testing; set to `public` when you explicitly want unattended public publishing.
- `YOUTUBE_CATEGORY_ID`: defaults to `28` (Science & Technology).
- `META_GRAPH_API_VERSION`: required for Instagram publishing; do not leave the `vXX.X` placeholder.

## Run

- Automatic: a successful Generate AI News Reel run triggers publishing to both platforms.
- Manual: Actions -> Publish AI News Reel -> Run workflow, choose `both`, `youtube`, or `instagram`, and type `PUBLISH` to confirm.
- The generated artifact must be available to the workflow. For manual runs, use the generation run ID and artifact name expected by the generator workflow.

YouTube defaults to private. Test with YouTube privacy set to private and a test Instagram account before enabling routine public publishing.

## Captions and attribution

The publisher uses the generated story title, source publisher and source URL to create the title, description, caption and hashtags. Hashtags are topic-relevant defaults, not guaranteed reach or popularity rankings. Check that your use of the underlying source material complies with its licensing and attribution requirements.

This is organic content publishing, not paid advertising. It does not create ad campaigns, spend budget, or guarantee reach.

## Operational notes

- Instagram direct upload requires an eligible professional account, correct app permissions, and a supported Meta Graph API version.
- The generated video must meet Meta's current Reels requirements. The generator targets 1080x1920 H.264/AAC at 60 seconds.
- Instagram and YouTube can fail independently; inspect the Actions logs and the publishing report artifact.
- Keep publishing secrets restricted to trusted maintainers and consider GitHub environment approvals for public publishing.
