import { Injectable } from '@angular/core';
import { initializeApp } from 'firebase/app';
import {
  getAuth,
  onAuthStateChanged,
  signInAnonymously,
  type User,
} from 'firebase/auth';

import { firebaseConfig } from './firebase-config';

/**
 * Invisible authentication: signs in anonymously on first load so the user
 * never sees a login screen, but every request still carries a verifiable
 * Firebase ID token with a stable uid (sessions, rate limiting, abuse control).
 * Linking to a Google account later keeps the same uid and history.
 */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly auth = getAuth(initializeApp(firebaseConfig));

  private readonly user = new Promise<User>((resolve) => {
    onAuthStateChanged(this.auth, (user) => {
      if (user) {
        resolve(user);
      }
    });
    signInAnonymously(this.auth).catch((err) =>
      console.error('Anonymous sign-in failed', err),
    );
  });

  /** Resolves to a fresh ID token; Firebase refreshes it transparently. */
  async idToken(): Promise<string> {
    return (await this.user).getIdToken();
  }
}
