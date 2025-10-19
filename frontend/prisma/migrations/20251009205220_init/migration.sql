-- CreateTable
CREATE TABLE "History" (
    "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    "coin" TEXT NOT NULL,
    "e1fr" REAL NOT NULL,
    "e2fr" REAL NOT NULL,
    "e1price" REAL NOT NULL,
    "e2price" REAL NOT NULL,
    "long" TEXT NOT NULL,
    "short" TEXT NOT NULL,
    "timestamp" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
