# FreeMail Mobile

This directory owns the future FreeMail mobile client.

The mobile client is part of the FreeMail product scope, but it should start after the server/admin/web API contracts are stable enough to avoid throwaway native work.

Expected scope:

- iOS and Android client.
- Secure session management.
- Inbox, message read, compose, reply, forward, search, folders/labels, and attachments.
- Offline-capable mail cache.
- Push notification path after server event contracts are available.

Candidate stacks:

- React Native with Expo.
- Flutter.

The implementation decision belongs in a future ADR before the first mobile code lands.
