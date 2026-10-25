import js from "@eslint/js";
import jsdoc from "eslint-plugin-jsdoc";
import noUnsanitized from "eslint-plugin-no-unsanitized";
import reactHooks from "eslint-plugin-react-hooks";
import security from "eslint-plugin-security";
import sonarjs from "eslint-plugin-sonarjs";
import globals from "globals";
import tseslint from "typescript-eslint";

/**
 * Flat ESLint configuration for the Apsor Archive frontend.
 *
 * TypeScript's recommended set handles syntax and type hygiene; the remaining
 * plugins guard React hook ordering, DOM injection, unsafe Node patterns, and
 * copy-paste-prone sonar rules. Generated Orval output is ignored because it is
 * machine-authored and regenerated.
 */
export default tseslint.config(
  {
    ignores: [
      "dist/**",
      "node_modules/**",
      "src/app/generated-apis-types/**",
      "*.tsbuildinfo",
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx,js}"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
    plugins: {
      "react-hooks": reactHooks,
      jsdoc,
      "no-unsanitized": noUnsanitized,
      security,
      sonarjs,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      ...sonarjs.configs.recommended.rules,
      ...security.configs.recommended.rules,
      "no-console": ["error", { allow: ["warn", "error"] }],
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/consistent-type-imports": [
        "error",
        { prefer: "type-imports", fixStyle: "inline-type-imports" },
      ],
      "no-unsanitized/method": "error",
      "no-unsanitized/property": "error",
      "jsdoc/check-alignment": "error",
      "jsdoc/check-param-names": "error",
      "jsdoc/check-tag-names": "error",
      "jsdoc/no-undefined-types": "off",
      "jsdoc/check-types": "off",
      // Static object indexing is idiomatic here (icon maps, route metadata) and
      // does not accept user-controlled keys anywhere in this codebase.
      "security/detect-object-injection": "off",
      // The frontend never reads the filesystem.
      "security/detect-non-literal-fs-filename": "off",
      // Repeated English labels are part of the editorial voice.
      "sonarjs/no-duplicate-string": "off",
      "sonarjs/cognitive-complexity": ["error", 24],
    },
  },
);
