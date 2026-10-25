/**
 * Compares every locale namespace against the English source of truth and
 * fails when a key is missing or extra. Empty placeholder namespaces pass.
 */
import {
  LOCALES,
  NAMESPACES,
  compareLocaleKeys,
  getLocaleKeyCount,
  getNamespaceKeys,
} from "../src/app/i18n/locales/index.ts";

const line = (message = ""): void => {
  process.stdout.write(`${message}\n`);
};

line("i18n key check · en is the source of truth");
for (const locale of LOCALES) {
  line(`  ${locale}: ${getLocaleKeyCount(locale)} keys`);
}

const emptyNamespaces = NAMESPACES.filter(
  (namespace) => getNamespaceKeys("en", namespace).length === 0,
);
if (emptyNamespaces.length > 0) {
  line(`  placeholder namespaces: ${emptyNamespaces.join(", ")}`);
}

let failures = 0;
for (const locale of LOCALES) {
  if (locale === "en") {
    continue;
  }
  const report = compareLocaleKeys(locale);
  for (const namespace of NAMESPACES) {
    const { missing, extra } = report[namespace];
    if (missing.length === 0 && extra.length === 0) {
      continue;
    }
    failures += 1;
    line(`\n[${locale}] ${namespace}`);
    if (missing.length > 0) {
      line(`  missing (${missing.length}):`);
      for (const key of missing) {
        line(`    - ${key}`);
      }
    }
    if (extra.length > 0) {
      line(`  extra (${extra.length}):`);
      for (const key of extra) {
        line(`    + ${key}`);
      }
    }
  }
}

if (failures > 0) {
  line(`\ni18n check failed: ${failures} namespace mismatch(es).`);
  process.exitCode = 1;
} else {
  line("\ni18n check passed: all locale namespaces match en.");
}
