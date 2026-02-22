import feather from "feather-icons";
import m from "mithril";

import "./bookmarks.css";
import * as rpc from "./rpc";

const LoadingSpinner = {
  view() {
    return m("div.spinner-container", [m("div.spinner")]);
  },
};

const APPEAL_HIGH = "high";
const READING_TIME_LONG = "long";
const READING_TIME_SHORT = "short";

const TagsPanel = {
  view(
    vnode: m.Vnode<{
      tagCounts: [string, number][];
      selectedTag: string | null;
      onSelectTag: any;
    }>,
  ) {
    const { tagCounts, selectedTag, onSelectTag } = vnode.attrs;

    return m("div.tag-filter-section", [
      m("div.tag-filter-badges", [
        tagCounts.map(([tag, count]) =>
          m(
            "button.tag-filter-badge",
            {
              class: selectedTag === tag ? "selected" : "",
              onclick: () => onSelectTag(tag),
            },
            `${tag} (${count})`,
          ),
        ),
      ]),
    ]);
  },
};

const ControlPanel = {
  view(
    vnode: m.Vnode<{ bookmarksCount: number; onRefresh: any; onShuffle: any }>,
  ) {
    const { bookmarksCount, onRefresh, onShuffle } = vnode.attrs;
    const s = bookmarksCount === 1 ? "" : "s";

    return m("div.control-panel", [
      m("span.bookmarks-count", `${bookmarksCount} bookmark${s}`),
      m("div.buttons", [
        m(
          "button.icon-btn.refresh",
          { onclick: () => onRefresh() },
          m.trust(feather.icons["refresh-cw"].toSvg({ size: 16 })),
        ),
        m(
          "button.icon-btn.shuffle",
          { onclick: () => onShuffle() },
          m.trust(feather.icons.shuffle.toSvg({ size: 16 })),
        ),
      ]),
    ]);
  },
};

const EditableBookmarkFields = {
  view(vnode: m.Vnode<{ bookmarkId: number; editingBookmarks: any }>) {
    const { bookmarkId, editingBookmarks } = vnode.attrs;
    const displayBookmark = editingBookmarks[bookmarkId];

    return [
      m("div.url-row", [
        m("label", "url:"),
        m("input", {
          value: displayBookmark.url,
          oninput: (e: InputEvent) => {
            editingBookmarks[bookmarkId].url = (
              e.target as HTMLInputElement
            ).value;
          },
          placeholder: "bookmark URL",
        }),
      ]),
      m("div", [
        m("label", "reading time:"),
        m(
          "select.reading-time",
          {
            value: displayBookmark.readingTime || "",
            onchange: (e: InputEvent) => {
              editingBookmarks[bookmarkId].readingTime = (
                e.target as HTMLInputElement
              ).value;
            },
          },
          [
            m("option", { value: "" }, "none"),
            m("option", { value: READING_TIME_SHORT }, "short"),
            m("option", { value: READING_TIME_LONG }, "long"),
          ],
        ),
      ]),
      m("div", [
        m("label", "appeal:"),
        m(
          "select.appeal-select",
          {
            value: displayBookmark.appeal || "",
            onchange: (e: InputEvent) => {
              editingBookmarks[bookmarkId].appeal = (
                e.target as HTMLInputElement
              ).value;
            },
          },
          [
            m("option", { value: "" }, "none"),
            m("option", { value: APPEAL_HIGH }, "high"),
          ],
        ),
      ]),
    ];
  },
};

function getDomain(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return "";
  }
}

function getDaysOld(dateAdded: string): string {
  if (!dateAdded) return "";
  const now = new Date();
  const added = new Date(dateAdded);
  const diffTime = Math.abs(now.getTime() - added.getTime());
  const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return "today";
  if (diffDays === 1) return "1 day ago";
  return `${diffDays} days ago`;
}

type Bookmark = rpc.Bookmark;

const BookmarkItem = {
  view(
    vnode: m.Vnode<{
      bookmark: Bookmark;
      isEditing: boolean;
      displayBookmark: Bookmark;
      editingBookmarks: any;
      onStartEditing: (bookmark: Bookmark) => void;
      onSaveEditing: (bookmark: Bookmark) => void;
      onCancelEditing: (bookmark: Bookmark) => void;
      onArchive: (bookmark: Bookmark, reason: string) => void;
      onUnarchive: (bookmark: Bookmark) => void;
    }>,
  ) {
    const {
      bookmark,
      isEditing,
      displayBookmark,
      editingBookmarks,
      onStartEditing,
      onSaveEditing,
      onCancelEditing,
      onArchive,
      onUnarchive,
    } = vnode.attrs;

    const isArchived = bookmark.reasonArchived !== "";

    const sortedTags = displayBookmark.tags.slice();
    sortedTags.sort(sortAsc);

    return m(
      "div.bookmark-item",
      {
        class: (isArchived ? "archived" : "") + (isEditing ? " editing" : ""),
        key: bookmark.bookmarkId,
      },
      [
        m("div.bookmark-header", [
          displayBookmark.appeal === APPEAL_HIGH && !isEditing
            ? m("span.appeal-star", "★")
            : null,
          m("div.bookmark-title-container", [
            isEditing
              ? m("input.bookmark-title", {
                  value: displayBookmark.title,
                  oninput: (e: InputEvent) => {
                    editingBookmarks[bookmark.bookmarkId].title = (
                      e.target as HTMLInputElement
                    ).value;
                  },
                  placeholder: "Bookmark title",
                  oncreate: (vnode) => {
                    (vnode.dom as HTMLInputElement).select();
                  },
                })
              : [
                  m(
                    "a.bookmark-title",
                    { href: displayBookmark.url, target: "_blank" },
                    bookmark.title,
                  ),
                  bookmark.readingTime === READING_TIME_LONG
                    ? " ⏳"
                    : bookmark.readingTime === READING_TIME_SHORT
                      ? " ⚡️"
                      : "",
                  m("div.subtitle", [
                    m("strong", getDomain(displayBookmark.url)),
                    " – bookmarked ",
                    m("strong", getDaysOld(bookmark.timeCreated)),
                    " (",
                    m("span.source", bookmark.source),
                    ")",
                  ]),
                ],
          ]),
          m("div.bookmark-actions", [
            isArchived
              ? m(
                  "button.icon-btn",
                  {
                    onclick: () => onUnarchive(bookmark),
                    title: "Unarchive bookmark",
                  },
                  /* kind of like an undo icon */
                  m.trust(feather.icons["corner-up-left"].toSvg({ size: 16 })),
                )
              : !isEditing
                ? [
                    m(
                      "button.icon-btn.archive-btn",
                      {
                        onclick: () => onArchive(bookmark, "read"),
                        title: "Archive bookmark",
                      },
                      m.trust(feather.icons.archive.toSvg({ size: 16 })),
                    ),
                    m(
                      "button.icon-btn.delete-btn",
                      {
                        onclick: () => onArchive(bookmark, "deleted"),
                        title: "Delete bookmark",
                      },
                      m.trust(feather.icons.trash.toSvg({ size: 16 })),
                    ),
                    m(
                      "button.icon-btn",
                      {
                        onclick: () => onStartEditing(bookmark),
                        title: "Edit bookmark",
                      },
                      m.trust(feather.icons["edit-2"].toSvg({ size: 16 })),
                    ),
                  ]
                : [
                    m(
                      "button.icon-btn",
                      {
                        onclick: () => onSaveEditing(bookmark),
                        title: "Save changes",
                      },
                      m.trust(feather.icons.save.toSvg({ size: 16 })),
                    ),
                    m(
                      "button.icon-btn",
                      {
                        onclick: () => onCancelEditing(bookmark),
                        title: "Cancel edit",
                      },
                      m.trust(feather.icons.x.toSvg({ size: 16 })),
                    ),
                  ],
          ]),
        ]),

        m("div.bookmark-details", [
          isEditing
            ? m(EditableBookmarkFields, {
                bookmarkId: bookmark.bookmarkId,
                editingBookmarks,
              })
            : null,
          m("div.bookmark-tags", [
            isEditing
              ? [
                  m("div.tag-list", [
                    m("label", "tags:"),
                    [
                      sortedTags.map((tag) =>
                        m("span.tag.editable", [
                          tag,
                          m(
                            "button.remove-tag",
                            {
                              onclick: () => {
                                const tags =
                                  editingBookmarks[bookmark.bookmarkId].tags;
                                const index = tags.indexOf(tag);
                                if (index > -1) tags.splice(index, 1);
                              },
                            },
                            "×",
                          ),
                        ]),
                      ),
                    ],
                    m("div.add-tag", [
                      m("input.new-tag-input", {
                        placeholder: "Add new tag",
                        onkeypress: (e: KeyboardEvent) => {
                          if (e.key === "Enter") {
                            const newTag = (
                              e.target as HTMLInputElement
                            ).value.trim();
                            if (
                              newTag &&
                              !displayBookmark.tags.includes(newTag)
                            ) {
                              editingBookmarks[bookmark.bookmarkId].tags.push(
                                newTag,
                              );
                              (e.target as HTMLInputElement).value = "";
                            }
                          }
                        },
                      }),
                      m(
                        "button.btn",
                        {
                          onclick: (e: InputEvent) => {
                            const input = (
                              e.target as HTMLInputElement
                            ).parentNode?.querySelector(
                              ".new-tag-input",
                            ) as HTMLInputElement;
                            if (!input) {
                              return;
                            }

                            const newTag = input.value.trim();
                            if (
                              newTag &&
                              !displayBookmark.tags.includes(newTag)
                            ) {
                              editingBookmarks[bookmark.bookmarkId].tags.push(
                                newTag,
                              );
                              input.value = "";
                            }
                          },
                        },
                        "Add",
                      ),
                    ]),
                  ]),
                ]
              : m(
                  "div.tag-list",
                  sortedTags.map((tag) => m("span.tag", tag)),
                ),
          ]),
        ]),
      ],
    );
  },
};

const SPECIAL_TAG_HIGH_APPEAL = "@high-appeal";
const SPECIAL_TAG_LONG_READ = "@long-read";
const SPECIAL_TAG_SHORT_READ = "@short-read";

function sortAsc(a: any, b: any): number {
  if (a < b) {
    return -1;
  }

  if (a > b) {
    return 1;
  }

  return 0;
}

interface State {
  bookmarks: Bookmark[];
  filteredBookmarks: Bookmark[];
  selectedTag: string | null;
  loading: boolean;
  editingBookmarks: any;
  error: string;
}

const BookmarksApp = {
  oninit(vnode: m.Vnode<{}, State>): void {
    vnode.state.bookmarks = [];
    vnode.state.filteredBookmarks = [];
    vnode.state.selectedTag = null;
    vnode.state.loading = true;
    vnode.state.editingBookmarks = {};
    this.loadBookmarks(vnode.state);
  },

  startEditing(state: State, bookmark: Bookmark): void {
    state.editingBookmarks[bookmark.bookmarkId] = {
      ...bookmark,
      tags: [...bookmark.tags],
    };
  },

  cancelEditing(state: State, bookmark: Bookmark): void {
    delete state.editingBookmarks[bookmark.bookmarkId];
  },

  saveEditing(state: State, bookmark: Bookmark): void {
    const editedBookmark = state.editingBookmarks[bookmark.bookmarkId];
    this.updateBookmark(state, editedBookmark);
    delete state.editingBookmarks[bookmark.bookmarkId];
  },

  refreshBookmarks(state: State, apiResponse: any): void {
    state.bookmarks = apiResponse.bookmarks;
    this.applyFilter(state);
  },

  async loadBookmarks(state: State): Promise<void> {
    state.error = "";
    let response: rpc.LoadResponse;
    try {
      response = await m.request({
        method: "GET",
        url: "/api/load",
      });
      state.loading = false;
    } catch (error) {
      state.error = "failed to load bookmarks";
      state.loading = false;
      return;
    }
    this.refreshBookmarks(state, response);
  },

  async updateBookmark(state: State, bookmark: Bookmark): Promise<void> {
    state.error = "";
    let response: rpc.LoadResponse;
    try {
      const request: rpc.UpdateRequest = {
        bookmarkId: bookmark.bookmarkId,
        title: bookmark.title,
        url: bookmark.url,
        readingTime: bookmark.readingTime,
        appeal: bookmark.appeal,
        tags: bookmark.tags,
      };
      response = await m.request({
        method: "POST",
        url: "/api/update",
        body: request,
      });
    } catch (error) {
      state.error = `failed to update bookmark ${bookmark.bookmarkId} ('${bookmark.title}')`;
      return;
    }
    this.refreshBookmarks(state, response);
  },

  async archiveBookmark(
    state: State,
    bookmark: Bookmark,
    reason: string,
  ): Promise<void> {
    state.error = "";
    let response: rpc.LoadResponse;
    try {
      const request: rpc.ArchiveRequest = {
        bookmarkId: bookmark.bookmarkId,
        reason,
      };
      response = await m.request({
        method: "POST",
        url: "/api/archive",
        body: request,
      });
    } catch (error) {
      state.error = `failed to archive bookmark ${bookmark.bookmarkId} ('${bookmark.title}')`;
      return;
    }
    this.refreshBookmarks(state, response);
  },

  async unarchiveBookmark(state: State, bookmark: Bookmark): Promise<void> {
    state.error = "";
    let response: rpc.LoadResponse;
    try {
      const request: rpc.UnarchiveRequest = {
        bookmarkId: bookmark.bookmarkId,
      };
      response = await m.request({
        method: "POST",
        url: "/api/unarchive",
        body: request,
      });
    } catch (error) {
      state.error = `failed to un-archive bookmark ${bookmark.bookmarkId} ('${bookmark.title}')`;
      return;
    }
    this.refreshBookmarks(state, response);
  },

  getTagCounts(state: State): [string, number][] {
    const tagCountsMap = new Map();
    state.bookmarks.forEach((bookmark) => {
      if (bookmark.appeal === APPEAL_HIGH) {
        const key = SPECIAL_TAG_HIGH_APPEAL;
        tagCountsMap.set(key, (tagCountsMap.get(key) || 0) + 1);
      }

      if (bookmark.readingTime === READING_TIME_LONG) {
        const key = SPECIAL_TAG_LONG_READ;
        tagCountsMap.set(key, (tagCountsMap.get(key) || 0) + 1);
      }

      if (bookmark.readingTime === READING_TIME_SHORT) {
        const key = SPECIAL_TAG_SHORT_READ;
        tagCountsMap.set(key, (tagCountsMap.get(key) || 0) + 1);
      }

      bookmark.tags.forEach((tag) => {
        tagCountsMap.set(tag, (tagCountsMap.get(tag) || 0) + 1);
      });
    });
    const tagCounts = Array.from(tagCountsMap.entries());
    tagCounts.sort(sortAsc);
    return tagCounts;
  },

  applyFilter(state: State): void {
    if (state.selectedTag) {
      state.filteredBookmarks = state.bookmarks.filter((bookmark) => {
        if (state.selectedTag === SPECIAL_TAG_HIGH_APPEAL) {
          return bookmark.appeal === APPEAL_HIGH;
        } else if (state.selectedTag === SPECIAL_TAG_LONG_READ) {
          return bookmark.readingTime === READING_TIME_LONG;
        } else if (state.selectedTag === SPECIAL_TAG_SHORT_READ) {
          return bookmark.readingTime === READING_TIME_SHORT;
        } else if (state.selectedTag !== null) {
          return bookmark.tags.includes(state.selectedTag);
        } else {
          return true;
        }
      });
    } else {
      state.filteredBookmarks = state.bookmarks;
    }
  },

  selectTag(state: State, tag: string): void {
    state.selectedTag = state.selectedTag === tag ? null : tag;
    this.applyFilter(state);
  },

  shuffle(state: State): void {
    // courtesy of https://stackoverflow.com/questions/2450954/
    const array = state.bookmarks;
    let currentIndex = array.length;

    // While there remain elements to shuffle...
    while (currentIndex != 0) {
      // Pick a remaining element...
      let randomIndex = Math.floor(Math.random() * currentIndex);
      currentIndex--;

      // And swap it with the current element.
      [array[currentIndex], array[randomIndex]] = [
        array[randomIndex],
        array[currentIndex],
      ];
    }
  },

  view(vnode: m.Vnode<{}, State>) {
    if (vnode.state.loading) {
      return m(LoadingSpinner);
    }

    const tagCounts = this.getTagCounts(vnode.state);

    return m("div.bookmarks-app", [
      vnode.state.error ? m("div.error", `Error: ${vnode.state.error}`) : null,

      tagCounts.length > 0
        ? m(TagsPanel, {
            tagCounts,
            selectedTag: vnode.state.selectedTag,
            onSelectTag: (tag: string) => this.selectTag(vnode.state, tag),
          })
        : null,

      m(ControlPanel, {
        bookmarksCount: vnode.state.bookmarks.length,
        onRefresh: () => this.loadBookmarks(vnode.state),
        onShuffle: () => this.shuffle(vnode.state),
      }),

      m(
        "div.bookmarks-list",
        vnode.state.filteredBookmarks.map((bookmark) => {
          const isEditing = vnode.state.editingBookmarks[bookmark.bookmarkId];
          const displayBookmark = isEditing
            ? vnode.state.editingBookmarks[bookmark.bookmarkId]
            : bookmark;

          return m(BookmarkItem, {
            key: bookmark.bookmarkId,
            bookmark,
            isEditing,
            displayBookmark,
            editingBookmarks: vnode.state.editingBookmarks,
            onStartEditing: (bookmark: Bookmark) =>
              this.startEditing(vnode.state, bookmark),
            onSaveEditing: (bookmark: Bookmark) =>
              this.saveEditing(vnode.state, bookmark),
            onCancelEditing: (bookmark: Bookmark) =>
              this.cancelEditing(vnode.state, bookmark),
            onArchive: (bookmark: Bookmark, reason: string) =>
              this.archiveBookmark(vnode.state, bookmark, reason),
            onUnarchive: (bookmark: Bookmark) =>
              this.unarchiveBookmark(vnode.state, bookmark),
          });
        }),
      ),
    ]);
  },
};

m.mount(document.body, BookmarksApp);
