"use client";

import Image from "next/image";
import { useState } from "react";

import { useLocale } from "@/components/LocaleProvider";
import { useSession } from "@/components/SessionProvider";

/**
 * The signed-in visitor's picture: whatever Google gave us, over the first
 * letter of their name on the brand gradient.
 *
 * The letter is not a fallback that replaces the picture on failure, it is what
 * is underneath it: a picture that is slow, blocked or gone then costs nothing,
 * where a swap on `onError` leaves an empty circle for as long as the request
 * takes to fail. The letter is upper-cased in the reader's own locale, because
 * in Turkish the capital of "i" is "İ" and anything else is a different letter.
 */
export function UserAvatar({ size }: { size: number }) {
  const { locale } = useLocale();
  const { profile, me } = useSession();
  const [loaded, setLoaded] = useState(false);

  const name = profile?.name ?? me?.email ?? profile?.email ?? "?";
  const initial = name.trim().charAt(0).toLocaleUpperCase(locale);

  return (
    <span
      aria-hidden
      className="relative grid shrink-0 place-items-center overflow-hidden rounded-full bg-gradient-to-br from-accent-fill-from to-accent-fill-to font-semibold text-on-accent"
      style={{ width: size, height: size, fontSize: Math.round(size * 0.42) }}
    >
      {initial}
      {profile?.avatar && (
        <Image
          src={profile.avatar}
          alt=""
          width={size}
          height={size}
          onLoad={() => setLoaded(true)}
          className={`absolute inset-0 size-full object-cover transition-opacity duration-200 ${
            loaded ? "opacity-100" : "opacity-0"
          }`}
        />
      )}
    </span>
  );
}

/** The other side of the conversation: the mark, in a circle the size of a face. */
export function BrandAvatar({ size }: { size: number }) {
  return (
    <span
      aria-hidden
      className="grid shrink-0 place-items-center rounded-full bg-accent-soft ring-1 ring-accent/20"
      style={{ width: size, height: size }}
    >
      <Image
        src="/logo.png"
        alt=""
        width={206}
        height={256}
        style={{ height: Math.round(size * 0.58), width: "auto" }}
      />
    </span>
  );
}
