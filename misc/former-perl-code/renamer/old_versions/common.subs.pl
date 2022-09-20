#!/usr/local/bin/perl

use warnings;
use strict;
use IO::File;

my $PATH_SEP = '/';

sub Trim {
    # Takes a string, strips leading and trailing whitespace, and returns the string.
    my $x = shift;
    $x =~ s/^\s+//;
    $x =~ s/\s+$//;
    $x;
}


sub Shuffle {
    # Takes an array ref. Returns a ref to a shuffled list.
    # See my notes on the Fisher-Yates shuffle.
    my (@deck, $i, $j, $v);
    @deck = @{shift()};
    for ($i = @deck - 1; $i > 0; $i --){
        $j = int rand ($i + 1);
        $v = $deck[$i];
        $deck[$i] = $deck[$j];
        $deck[$j] = $v;
    }
    \@deck;
}


sub FileOpen {
    # Opens a file for reading, writing, writing-over, or appending.
    # Checks whether the file already exists (if MODE = w) and 
    # whether the open was successful.
    #
    # Takes 2 arguments:
    # 	"FILENAME", "MODE"   # modes: r w wo a
    # 
    # Returns a file handle, of the IO::File->new() variety.
    my ($h, $file, $mode, %opM);
    die "\nFileOpen() died: N of args.\n" unless @_ == 2;
    for ($file, $mode){
        $_ = shift;
        die "\nFileOpen() died: bad args.\n" unless defined and length;
    }
    %opM = (r => '', a  => '>> ', w => '> ', wo  => '> ');
    die "\nFileOpen() died: bad mode.\n" unless defined $opM{$mode};
    die "\nNot safe to write: $file.\n" if $mode eq 'w' and -e $file;
    $h = IO::File->new();
    $h->open($opM{$mode} . $file) or die "\nFileOpen() failed to open $file.\n";
    return $h;
}


sub ReadFile {
    # Args:     ("FILE NAME")
    # Returns:  [LIST OF ALL LINES FROM FILE]
    my ($file, $handle, @gulp);
    $file = shift;
    die "\nReadFile() used incorrectly.\n" unless length $file;
    $handle = FileOpen($file, 'r');
    @gulp = <$handle>;
    close $handle;
    return(\@gulp);
}


sub ReadDir {
    # This is a purposely streamlined routine -- compared to Files() -- that gets the
    # contents of a directory: files, subdirectories (excluding '.' and '..'), or
    # both files and subdirectories.
    # 
    # The routine returns an array reference to the list of contents. Note that the
    # values in the returned list are not full paths; rather, they are just the file
    # or subdirectory names. Note also that the routine won't gripe about bad paths;
    # rather, it simply returns an empty list.
    # 
    # The routine takes two arguments, the second optional:
    #     path  The directory to read (a trailing path separator is optional)
    #     type  1 = only subdirectories
    #           2 = only files
    #           0 = both (the default)

    my ($path, $type, $sep, @content);
    ($path, $type) = @_;
    $type = 0 unless defined $type;
    
    # Add the path seperator to the path, unless it's there already.
    $sep = $PATH_SEP;
    $path .= $sep unless substr($path, -1) eq $sep;

    # Read the directory.
    opendir (READDIRDIR, $path) or return [];
    @content = readdir READDIRDIR;
    closedir READDIRDIR;

    # Exclude the . and .. subdirectories.
    @content = grep { $_ ne '.' and $_ ne '..' } @content;

    # If requested, keep just directories or just files.
    if ($type == 2) {
        @content = grep -d "$path$sep$_", @content;
    } elsif ($type == 1) {
        @content = grep -f "$path$sep$_", @content;
    }
    return \@content;
}


sub Files {
    # Arguments
    # ---------
    #     ( LIST OF FILE/DIR NAMES WITH WILDCARDS, { dir   => t/F,
    #                                                all   => t/F,
    #                                                temp  => t/F,
    #                                                path  => PATH );
    #
    # LIST can be passed as a list, a reference, or any combination thereof 
    # (but the return value is always a reference).  The HASH is optional; if given, 
    # it must be last.
    # 
    # Return value
    # ------------
    #     [LIST OF FILE/DIR NAMES AFTER WILDCARD EXPANSION]
    # 
    # The function will remove any duplicates from the list.
    # 
    # Discussion
    # ----------
    #
    # This subroutine will generate a list of files and/or directories 
    # (the default is just files), expanding whenever the * or ? wildcards are detected.
    # The wildcard expansion not entirely Perlish or DOS-like.
    # The * symbol stands for zero or more arbitrary characters, and the ? symbol 
    # stands for exacly one arbitrary character.  If a character is specified, it is
    # required (thus, the DOS equivalence between * and *.* does not hold here).
    # The path names provided as arguments can be complete or relative to the
    # current directory.
    #
    # Use the hash to control behavior:
    #      dir  if true, returns just directories
    #      all  if true, returns both files and directories (overrides 'dir')
    #     temp  if true, does not weed out ~ hidden/temporary files; otherwise,
    #             they are weeded out unless an argument itself calls for
    #             files beginning with the ~ character.
    #     path  if this string has length, it is prepended to all of the file/dir
    #             pattern strings, before wildcard expansion (so the path can
    #             contain wildcards as well).
    my (@wild, @tempwild, @tame, @content, @ok, %seen,
        $r, $dir, $all, $temp, $path,
        $left, $right, $pat, $leftDir);

    ###
    #  Get arguments and subroutine parameters
    ###

    $_ = 0 for ($dir, $all, $temp);
    $path = '';
    if ( ref ( $_[-1] ) eq 'HASH' ){
        $r = pop;
        $temp = 1 if $r->{temp};
        $dir  = 1 if $r->{dir};
        $path = $r->{path} if defined $r->{path};
        if ( $r->{all} ){
            $all = 1;
            $dir = 0; # all overrides dir
        }
    }
    DieClean("\nFiles() used incorrectly.") unless @_;
    for (@_){
        if ( ref() eq 'ARRAY' ){
            push @wild, @$_;
        } else {
            push @wild, $_;
        }
    }

    if (length $path){
        $path =~ s/\\$//;
        $_ = join('\\', $path, $_) for @wild;
    }

    ###
    #  Wildcard expansion
    ###
    
    while (1){
        @tempwild = ();
        # Put items with wildcards in @tempwild; items without in @tame
        for my $w (@wild){
            if ( $w =~ /[\*\?]/ ){
                push @tempwild, $w;
            } else {
                push @tame, $w;
            }
        }
        last unless @tempwild; # No wildcards left; finished.
        @wild = ();            # Will hold expansions of @tempwild items.
        for my $t (@tempwild){

            ###
            #  Split string into 3 parts: left, pattern, and right
            ###

            # Search for wildcard and split string into left-right halves
            $t =~ /[\*\?]/g;
            $left = substr $t, 0, pos($t);
            $right = substr $t, pos($t);

            # Search left side for the last backslash
            $left =~ /.*\\/g;
            if ( pos($left) ){
                # Left side is everything up through last backslash.
                # The pattern is the rest.
                $pat = substr $left, pos($left);
                $left = substr $left, 0, pos($left);
            } else {
                # No backslashes, so no left side
                $pat = $left;
                $left = '';
            }

            # Search right side for the first backslash
            $right =~ /\\/g;
            if ( pos($right) ){
                # Right side is everything from backslash to end.
                # Append the rest to pattern.
                $pat .= substr $right, 0, pos($right) - 1;
                $right = substr $right, pos($right) - 1;
            } else {
                # No backslash, so no right side.
                # Append it all to pattern.
                $pat .= $right;
                $right = '';
            }

            ###
            #  Set directory and create regular expression
            ###

            # If there is a left side, it must be a directory.
            # Otherwise, use current directory
            if ( length $left ){
                next unless -d $left;
                $leftDir = $left;
            } else {
                $leftDir = '.';
            }

            # Convert wildcards into regular expressions
            $pat = quotemeta $pat;  # Backslash regex chars
            $pat =~ s/\\\*/.*/g;    # Convert * to .*
            $pat =~ s/\\\?/./g;     # Convert ? to .

            ###
            #  Read directory and keep items that meet pattern
            ###

            # Read the directory contents
            opendir (FILESDIRECTORY, $leftDir) or
                die "\nFiles() coulnd't open $leftDir.\n";
            @content = readdir FILESDIRECTORY;
            closedir FILESDIRECTORY;
            
            # Keep an item only if it:
            #  - exactly matches the search pattern, ignoring case
            #  - is not the . or .. directory
            #  - is a directory, if there is a right side
            #  - is not a hidden ~ file, unless these were requested
            #      via $temp or a leading ~ on the main argument
            @ok = ();
            for (@content){
                next unless /^$pat$/i;
                next if $_ eq '.' or $_ eq '..';
                next if length $right and !( -d "$left$_" );
                next if /^~/ and !( $temp or substr($pat, 0, 2) eq '\~' );
                push @ok, $_;
            }

            # Attach left & right sides to the valid contents
            push ( @wild, $left . $_ . $right ) for @ok;
        }
    }

    ###
    # Wrap-up
    ###

    # Keep all files and dirs, just dirs, or just files.
    if ($all){
        @tame = grep {-d or -f} @tame;
    } elsif ($dir){
        @tame = grep -d,  @tame;
    } else {
        @tame = grep -f,  @tame;
    }

    # Remove duplicates and return.
    @tame = grep { ! $seen{$_} ++ } @tame;
    return \@tame;
}


sub Stems {
    # Arguments
    # ---------
    # ( [LIST] or "STRING", { path => t/F,
    #                         ext  => t/F } )
    # 
    # First argument must be a LIST reference or a single string.
    # Hash ref and individual keys optional
    # 
    # Returns
    # -------
    # Either [LIST OF FILE STEMS] or "FILE STEM", depending on whether the first
    # argument was a LIST reference or a string.
    # 
    # Discussion
    # ----------
    # Extracts the file name stems from Windows-style file names.  It performs two
    # deletions, one from the beginning of a string (all chars up to and including
    # the last backslash), the other from the end (a period and 1-4 letters). The
    # second argument can be used to control behavior:
    # 
    #             path => if true, path will be kept
    #             ext  => if true, extension will be kept

    my ($r, @list, $path, $ext);
    ($path, $ext) = (0, 0);
    if ( ref($_[-1]) eq 'HASH' ){
        $r = pop;
        $path = 1 if $r->{path};
        $ext  = 1 if $r->{ext};
    }
    $r = shift;
    if ( ref($r) eq 'ARRAY' ){
        @list = @$r;
    } else {
        @list = ($r);
    }
    foreach my $li (@list){
        $li =~ s/^.*\\//             unless $path;
        $li =~ s/\.[a-z0-9]{1,4}$//i unless $ext;
    }
    if ( ref($r) eq 'ARRAY' ){
        return \@list;
    } else {
        return $list[0];
    }
}


sub YesNo {
    # Args:
    #     ( "MESSAGE", "REPLY" )
    #     Both optional.  REPLY defaults to 'y'.
    # Behavior:
    #     print 'MESSAGE '
    #     print '[y/n] ' unless REPLY arg is provided
    #     get user input
    #     return true if input equals REPLY

    my ($message, $ok, $reply);
    $message = shift;
    $ok = shift;
    unless (defined $ok){
        $message .= ' [y/n]';
        $ok = 'y';
    }
    print STDERR "$message ";
    chomp ($reply = <STDIN>);
    $reply eq $ok;
}


sub Tm {
    # Takes one or more string arguments and returns a corresponding
    # list of time values.
    #
    #     sec         0-59
    #     min         0-59
    #     hm          0-23
    #     hr          1-12
    #     ampm        'a.m.' or 'p.m.'
    #     mday        1-31
    #     mon         1-12
    #     month       name of month
    #     year        year
    #     wday        1-7 (Sunday = 1)
    #     weekday     name of weekday
    #     yday        1-366
    #     dst         0-1 (true if daylight savings time)

    my (@t, @month, @day, %timeVal, @ret);
    die "\nTm() not passed an argument.\n" unless @_;
    @t = localtime();
    @month = qw(January February March April May June July
                August September October November December);
    @day = qw(Sunday Monday Tuesday Wednesday Thursday Friday Saturday);
    %timeVal = (
        sec     => $t[0],
        min     => $t[1],
        hm      => $t[2],
        hr      => ($t[2] == 0 ? 12 : $t[2] > 12 ? $t[2] - 12 : $t[2]),
        ampm    => ($t[2] < 12 ? 'a.m.' : 'p.m.'),
        mday    => $t[3],
        mon     => $t[4] + 1,
        month   => $month[$t[4]],
        year    => $t[5] + 1900,
        wday    => $t[6] + 1,
        weekday => $day[$t[6]],
        yday    => $t[7] + 1,
        dst     => $t[8] ? 1 : 0,
    );
    for my $k (@_){
        die "\nTm() given invalid argument: $k\n" unless defined $timeVal{$k};
        push @ret, $timeVal{$k};
    }
    return @ret;
}

sub GetPassword {
    my ($pw);
    print STDERR 'Enter password: ';
    system "stty -echo";
    chomp ($pw = <STDIN>);
    print STDERR "\n";
    system "stty echo";
    return $pw;
}

1; 

