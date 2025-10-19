/*
  Warnings:

  - You are about to drop the column `timestamp` on the `History` table. All the data in the column will be lost.
  - Added the required column `apr` to the `History` table without a default value. This is not possible if the table is not empty.
  - Added the required column `diff` to the `History` table without a default value. This is not possible if the table is not empty.
  - Added the required column `priceDiffPct` to the `History` table without a default value. This is not possible if the table is not empty.

*/
-- RedefineTables
PRAGMA defer_foreign_keys=ON;
PRAGMA foreign_keys=OFF;
CREATE TABLE "new_History" (
    "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "coin" TEXT NOT NULL,
    "e1fr" REAL NOT NULL,
    "e2fr" REAL NOT NULL,
    "e1price" REAL NOT NULL,
    "e2price" REAL NOT NULL,
    "diff" REAL NOT NULL,
    "apr" REAL NOT NULL,
    "priceDiffPct" REAL NOT NULL,
    "long" TEXT NOT NULL,
    "short" TEXT NOT NULL
);
INSERT INTO "new_History" ("coin", "e1fr", "e1price", "e2fr", "e2price", "id", "long", "short") SELECT "coin", "e1fr", "e1price", "e2fr", "e2price", "id", "long", "short" FROM "History";
DROP TABLE "History";
ALTER TABLE "new_History" RENAME TO "History";
PRAGMA foreign_keys=ON;
PRAGMA defer_foreign_keys=OFF;
