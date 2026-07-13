#import <Foundation/Foundation.h>
#import <objc/runtime.h>
#import <objc/message.h>
#import <dlfcn.h>

/*
 * Probe Apple TLTransliterator for Gujarati.
 * Usage: probe_tl [wordlist.txt]
 * Reads roman words (one per line) from argv[1] or stdin.
 * Prints TSV: input<TAB>gujarati<TAB>type<TAB>lmScore
 */

int main(int argc, const char *argv[]) {
  @autoreleasepool {
    dlopen("/System/Library/PrivateFrameworks/Transliteration.framework/Transliteration", RTLD_NOW);
    Class Params = NSClassFromString(@"TLTransliteratorInitParameters");
    Class TL = NSClassFromString(@"TLTransliterator");
    if (!Params || !TL) {
      fprintf(stderr, "TLTransliterator unavailable\n");
      return 1;
    }

    id params = [Params new];
    [params setValue:[NSLocale localeWithLocaleIdentifier:@"gu"] forKey:@"locale"];
    [params setValue:@YES forKey:@"useLanguageModel"];
    [params setValue:@NO forKey:@"useSeq2SeqModel"];
    id tl = ((id(*)(id, SEL, id))objc_msgSend)([TL alloc], @selector(initWithParameters:), params);
    if (!tl) {
      fprintf(stderr, "initWithParameters failed\n");
      return 1;
    }

    NSMutableArray<NSString *> *words = [NSMutableArray array];
    if (argc >= 2) {
      NSString *path = [NSString stringWithUTF8String:argv[1]];
      NSString *text = [NSString stringWithContentsOfFile:path encoding:NSUTF8StringEncoding error:nil];
      for (NSString *line in [text componentsSeparatedByCharactersInSet:[NSCharacterSet newlineCharacterSet]]) {
        NSString *w = [line stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
        if (w.length > 0 && ![w hasPrefix:@"#"]) [words addObject:w];
      }
    } else {
      char buf[4096];
      while (fgets(buf, sizeof(buf), stdin)) {
        NSString *line = [[NSString stringWithUTF8String:buf]
            stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
        if (line.length > 0 && ![line hasPrefix:@"#"]) [words addObject:line];
      }
    }

    for (NSString *inp in words) {
      NSArray *cands = ((id(*)(id, SEL, id, id, unsigned long))objc_msgSend)(
          tl, @selector(generateCandidatesForInputWord:candidateContext:maxCandidatesCount:),
          inp, nil, (unsigned long)8);
      for (id c in cands) {
        NSInteger type = [[c valueForKey:@"type"] integerValue];
        // Skip emoji (type 3)
        if (type == 3) continue;
        NSString *tw = [c valueForKey:@"transliteratedWord"];
        if (!tw.length) continue;
        id lm = [c valueForKey:@"lmScore"];
        printf("%s\t%s\t%ld\t%s\n",
               inp.UTF8String,
               tw.UTF8String,
               (long)type,
               [[lm description] UTF8String]);
      }
    }
  }
  return 0;
}
