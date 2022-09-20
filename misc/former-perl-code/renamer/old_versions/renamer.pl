#! /usr/bin/env perl

use warnings;
use strict;

use File::Basename qw(dirname);
use lib dirname($0) . '/modules';
require 'common.subs.pl';

use feature qw(say);
use Data::Dumper qw(Dumper);
$Data::Dumper::Indent = 1;
sub xxx { say Dumper(@_) }

my $s = "foo/bar/fub";

my $sep = '/';

$s =~ s/$sep/_/g;

say $s;



exit;

=pod
Improvements:
    - put the main functionality in a module
    - then provide a command-line front-end
    - make it work on Windows or Unix
    - search CPAN for design ideas
    - better logging

Interface:
    - File type:
        - files
        - dirs
        - both

    - Operation
        - move/rename
        - copy
        - symlink
        - hardlink

    - Modes
        - real
        - dryrun

        - interactive: either fully or for overwrites
        - force
        - backup: user-controlled suffix in event of conflicts

        - verbose

    - Input structure
        - just ORIG names
        - ORIG and NEW names as a list (all ORIG, then all NEW)
        - ORIG and NEW names side-by-side (using delimitor)

    - Input source
        - ARGV
        - STDIN
        - file
        - clipboard
        - call to `find`
        - a shell pattern
        - a Files() pattern

    - Transformations
        - Don't restrict to just one transformation.
        - Eval
        - Remove common leading or trailing text
        - Placeholder pattern, including iterators.
        - Evaluate user's code in a context that includes useful helper functions:
            http://search.cpan.org/~swestrup/App-FileTools-BulkRename-0.07/bin/brn
        - Allow user to define scriptlets in a directory:
            https://metacpan.org/pod/distribution/App-perlmv/bin/perlmv
            ~/.perlmv/scriptlets/

    - Transformations applied to
        - ORIG
        - NEW

=cut

=pod
This program renames/moves files or directories.

Methods to specify the items to be renamed:
    batch file
        - to get response
        - to get files names
    clipboard
    pattern with wildcards for Files() [files are sorted, case-insensitive]

Methods to perform the renaming:
    batch file
        - to get response
        - to get files names
    clipboard
    remove common leading text
    eval() code to operate on $_, the current name
    pattern, using markers to represent components of the current names
        *f full name, with path
        *p path, including the trailing '\\'
        *n name, with extension
        *s stem
        *e extension
        *i iterator

The functionality of pattern renaming can be included in the other methods. For example, the new file names in the batch file or the clipboard could include the pattern symbols.

The batch file's location is specified in my Perl constants. Here's the file's structure:
	- blank lines are ignored
	- leading and trailing whitespace is ignored
	- @old = lines before separator [specified in Perl constants]
	- @new = lines after separator

The program uses the following variables:
    $n         General purpose scalar.
    $sep       Separator used in the batch file.

    $dir       1 if renaming directories; 0 for files.
    $meth      User input specifying renaming method.
    $shiftit   Flag to indicate whether to shift() the first 
               value of @old or @new (applicable when user supplies
               a response via the batch file). Later used to
               keep track of whether to increment the file renaming
               iterator.

    @old      List of items to be renamed.
    @new       A parallel list of the new names.
    @notfound  Items in @old that don't exist.

    @display   List of old and new names for user confirmation.
               Later, an error report.

    %uni  Used to verify that new file names are unique.

    %cn  Components used in pattern renaming (based on current name)
        f full name, with path
        p path, including a trailing '\'
        n name
        s stem
        e extension
        i iterator  [starting value specified by user]
=cut

###
# Set up
###
my ($h, $n, $dir, $meth, $shiftit,
    @old, @new, @notfound,
    @display, %uni, %cn, $report,
);
print Head("Rename or move files and directories", {over => 1});

my $SCRIPT_DIR       = dirname $0;
my $BATCH_RENAME     = $SCRIPT_DIR . '/renamer_logs/rename_batch.txt';
my $BATCH_RENAME_LOG = $SCRIPT_DIR . '/renamer_logs/rename_log.txt';
my $BATCH_RENAME_SEP = '**END**';

###
# Read batch file
###
$n = ReadRenameBatchFile();
@old = @{$n->[0]};
@new = @{$n->[1]};
print "\nBatch file read:\n",
    '    @old: ', scalar(@old), "\n",
    '    @new: ', scalar(@new),  "\n";    

###
# Rename files or directories?
###
print "\nRename:
    [f]iles
    [d]irectories
    [c]lear log
    [s]show log
";
while (1){
    print "=> ";
    $dir = lc Trim($dir = <STDIN>);
    DieIfNoInput($dir);
    last if $dir =~ /^[fdcs]$/;
}
if ($dir eq 'c'){
    # Just clear the log.
    @old = @new = ();
    WriteRenamingLog(1);
    die "\nLog cleared.\n";
}
if ($dir eq 's'){
    # Just show the log.
    @old = @new = ();
    ShowRenamingLog();
    exit;
}

$dir = $dir eq 'd' ? 1 : 0;

###
# Select items to be renamed.
###
print "\nSelecting items to be renamed:
    [g]et response from batch file
    [b]atch file
    [c]lipboard
    [cc] clipboard columns
    p PATTERN    [with wildcards; results sorted, case-insensitive]\n";
while (1){
    print "=> ";
    $meth = Trim($meth = <STDIN>);
    DieIfNoInput($meth);
    # Get response from batch file
    $shiftit = 0;
    if ($meth eq 'g'){
        $meth = $old[0] if @old;
        $shiftit = 1;
    }
    # Get the items
    if ($meth eq 'b'){
        # Batch file
        shift @old if $shiftit;
        last;
    } elsif ($meth eq 'c'){
        # Clipboard.
        @old = split "\r\n", Trim(Win32::Clipboard::GetText());
        last;
    } elsif ($meth eq 'cc'){
        # Clipboard columns.
        @old = split "\r\n", Trim(Win32::Clipboard::GetText());
        for (@old){
            die "\nBad column input: $_\n" unless /^([^\t]+)\t([^\t]+)$/;
            $_ = $1;
        }
        last;
    } elsif ($meth =~ /^p +(.+)$/) {
        # File pattern
        $meth = $1;
        @old = sort {lc $a cmp lc $b} @{ Files($meth, {dir => $dir}) };
        last;
    }
}

####
# Verify that the items were found.
####
die "\nNo items found.\n" unless @old;
@notfound = grep { ! ItemExists($_) } @old;
if (@notfound){
    PrintMore("\nSome items weren't found:", map("    $_", @notfound));
    die "\nNo items renamed.\n";
}
print "\nItems found: ", scalar(@old), "\n";
PrintMore(map "    $_", @old);
print "\nPress ENTER to proceed to the next step => ";
<STDIN>;

###
# Determine the renaming method, and create new names.
###
print "\nRenaming method:
    [g]et response from batch file
    [b]atch file
    [c]lipboard
    [cc] clipboard columns
    [r]emove common leading text
    e CODE     [operating on \$_ in an eval() call]
    p PATTERN  [using markers for components of the current names]
        *f full name, with path     
        *p path                                  *p\\  *s.*e
        *n name, with extension                       _____
        *s stem                                        *n
        *e extension                             __________
        *i iterator                                 *f
";
while (1){
    print "=> ";
    $meth = Trim($meth = <STDIN>);
    DieIfNoInput($meth);
    # Get response from batch file
    $shiftit = 0;
    if ($meth eq 'g'){
        $meth = $new[0] if @new;
        $shiftit = 1;
    }
    # Renaming method
    if ($meth eq 'b'){
        # Batch file.
        shift @new if $shiftit;
        last;
    } elsif ($meth eq 'c'){
        # Clipboard.
        @new = split "\r\n", Trim(Win32::Clipboard::GetText());
        last;
    } elsif ($meth eq 'cc'){
        # Clipboard columns.
        @new = split "\r\n", Trim(Win32::Clipboard::GetText());
        for (@new){
            die "\nBad column input: $_\n" unless /^([^\t]+)\t([^\t]+)$/;
            $_ = $2;
        }
        last;
    } elsif ($meth eq 'r'){
        # Remove common leading text
        @new = @old;
        $n = 0;
        while (1){
            # Determine N of leading characters common to all file names.
            $n ++;
            last unless 
                scalar (grep
                        { substr($_, 0, $n) eq substr($old[0], 0, $n) }
                        @old
                ) == scalar (@old);
        }
        $n --;
        die "\nNo files renamed. No common text.\n" unless $n > 0;
        @new = map substr($_, $n), @old;
        last;
    } elsif ( $meth =~ /^p +(.+)$/ ){
        # Pattern.
        @new = map $1, @old;
        last;
    } elsif ( $meth =~ /^e +(.+)$/ ){
        # Eval code.
        $meth = $1;
        @new = @old;
        eval $meth for @new;
        last;
    }
}

###
# Verify that the lists are the same size
###
die "\nNo items renamed: lists must contain the same number of elements.\n"
    unless $#old == $#new;

###
# Process any patterns in @new.
###
if ( join('', @new) =~ /\*i/ ){
    print "\nEnter starting value for iterator (letters and digits only):\n";
    while (1){
        print "=> ";
        $cn{i} = Trim($cn{i} = <STDIN>);
        DieIfNoInput($cn{i});
        last if $cn{i} =~ /^[a-z0-9]+$/i;
    }
}
for my $i (0 .. $#old){
    # Skip files without any patterns.
    next unless $new[$i] =~ /\*[fpnsei]/;
    # Get the current path, name, stem, and extension
    $old[$i] =~ /^
        ((.+)\\)?
        (
            (.+?)
            ( \. ([a-z0-9]{1,4}) )?
        )
        $/xi
        or die "\nFailed pattern match on current file: $old[$i]\n";
    $cn{f} = $&;
    $cn{p} = defined $1 ? $2 : '';
    $cn{n} = $3;
    $cn{s} = $4;
    $cn{e} = defined $6 ? $6 : '';
    # Check for an iterator.
    $shiftit = $new[$i] =~ /\*i/ ? 1 : 0;
    # Replace pattern elements
    $new[$i] =~ s/\*$_/$cn{$_}/g for qw(f p n s e i);
    # Increment the iterator, if the item contained one.
    $cn{i} ++ if $shiftit;
}

###
# Verify the the new names are unique.
###
for my $f (@new){
    die "\nNo items renamed: new names must be unique.\n    $f\n"
        if $uni{$f};
    $uni{$f} = 1;
}

###
# Verify that target directories exist
###
for my $f (@new){
    if ($f =~ /^(.+)\\.+$/){
        die "\nNo items renamed: target directory doesn't exist.\n    $1\n"
            unless -d $1;
    }
}

###
# Display a list showing old names and new names.
# Get user verification.
###
for my $i (0 .. $#old){
#    push @display, "    OLD => $old[$i]\n    NEW => $new[$i]\n"
    push @display, "    => $old[$i]\n       $new[$i]"
        unless $old[$i] eq $new[$i];
}
die "\nNo items renamed: old and new names are the same.\n" unless @display;
PrintMore("\nItems to be renamed: " . scalar(@display) . "\n", @display, {scroll => 18});
die "\nNo items renamed.\n" unless
    YesNo("\nEnter 'yes' to perform the renaming =>", 'yes');

###
# Perform the renaming
###
@display = ();
for my $i (0 .. $#old){
    if ( $old[$i] eq $new[$i] ){
        # Do nothing
    } elsif ( ItemExists($new[$i]) ){
        if ( lc $old[$i] eq lc $new[$i] ){
            # Only a case change.
            rename $old[$i], $new[$i];
        } else {
            # Can't rename: item exists.
            push @display, "EXISTS: old => $old[$i]",
                           "        new => $new[$i]";
        }
    } else {
        unless ( rename $old[$i], $new[$i] ){
            # Failed rename.
            push @display, "FAILED: old => $old[$i]",
                           "        new => $new[$i]";
        }
    }
}

###
# Report results
###
WriteRenamingLog();
sub WriteRenamingLog {
    $report = $BATCH_RENAME_LOG;
    $h = FileOpen($report, 'wo');
    $report = Stems($report, {ext => 1});
    print $h "$_\n" for @old, '', $BATCH_RENAME_SEP, '', @new;
    unless (shift){
        if (@display){
            print $h "$_\n" for '', "==============", '', @display;
            print "\nThe items were renamed, except as noted: $report\n";
        } else {
            print "\nThe items were renamed: $report\n";
        }
    }
    close $h;
}

sub ShowRenamingLog {
    @ARGV = ($BATCH_RENAME_LOG);
    print "\nRenaming log:\n\n";
    print while <>;
}

###
# Subroutine to quit if user inputs a blank line.
###
sub DieIfNoInput {
    die "\nNo items renamed.\n" unless length(shift);
}

###
# Subroutine to check if an item exists.
###
sub ItemExists {
    my $f = shift;
    $dir ? (-d $f) : (-f $f);
}

####
# Reads my batch renaming file and returns a ref to a list of lists:
#     [ [OLD NAMES], [NEW NAMES] ]
# The lines are trimmed of leading and trailing white space.
####
#
sub ReadRenameBatchFile {
    my (@old, @new);
    @new = grep /\S/, @{ ReadFile($BATCH_RENAME) };
    $_ = Trim($_) for @new;
    while (@new){
        if ($new[0] eq $BATCH_RENAME_SEP){
            shift @new;
            last;
        }
        push @old, shift(@new);
    }
    return [\@old, \@new];
}


sub Head {
    # This function takes string and returns that string ready for heading-style
    # printing.  The argument need not include a newline.  The default is simply an
    # underlined heading.
    # 
    #     over      if true, puts a line above heading also
    #     caps      if true, makes heading all caps
    #     nonew     if true, the returned string will not include final newline.
    #     indent    if a positive integer, heading is indented N tab stops
    # 
    # When you call this function as part of a print() statement using a handle from
    # IO::File handle, you can get an error if Head() immediately follows the handle.
    # 
    #     print $h       Head("Heading")  ; # Gives error; expects operator.
    #     print $h "",   Head("Heading")  ; # No error.
    #     print $h     ( Head("Heading") ); # Also no error.


    my ($x, $line, $r, $over, $caps, $nonew, $indent);
    $x = shift;
    chomp $x;
    $line = ("-" x length($x)) . "\n";
    $x .= "\n";
    $r = shift;
    $_ = 0 foreach ($over, $caps, $nonew, $indent);
    if (ref $r eq "HASH"){
        $over   = 1            if $r->{over};
        $caps   = 1            if $r->{caps}; 
        $nonew  = 1            if $r->{nonew}; 
        $indent = $r->{indent} if $r->{indent} and
                                  $r->{indent} !~ /\D/;        
    }
    $x =~ tr/a-z/A-Z/ if $caps;
    $_ = ("\t" x $indent) . $_ foreach ($line, $x);
    $x = join( "", $over ? $line : "", $x, $line );
    chomp $x if $nonew;
    return $x;
}

sub PrintMore {
    # Arguments
    # ---------
    #     ( LIST, { scroll  => INTEGER,
    #               begin   => INTEGER,
    #               end     => INTEGER,
    #               prefix  => STRING,
    #               number  => t/F,
    #               nonew   => t/F,
    #               final   => t/F } )
    # The LIST is required.  It can be provided as a list, a reference, or any
    # combination thereof.  The hash ref and individual keys are optional.  The
    # function will die() if given:  no list to print; something other than a
    # positive integer for the integer arguments; or a scroll value less than 1.
    # Within those constraints, the function will not gripe about odd begin and end
    # values (e.g., when they exceed the subscript range of the list to be printed or
    # when they imply that nothing gets printed).
    # 
    # Discussion
    # ----------
    # This function prints a list, pausing every N elements for the user to press
    # ENTER.  The hash can be used to control printing behavior [defaults shown]:
    # 
    #     scroll    number of elements to print between pauses [20]
    #     begin     subscript of first element to be printed [0]
    #     end       subscript of last element to be printed [last subscript]
    #     prefix    string to print before each element [empty]
    #     number    if true, elements will be numbered [F]
    #     nonew     if true, newlines not printed after each element [F]
    #     final     if true, a final ENTER will be required of user [F]
    # 
    # AN ALTERNATIVE TECHNIQUE
    # ------------------------
    # open MORE, "|more" or die "oops\n";
    # print MORE "$_\n" for 0 .. 200;
    # close MORE;

    my (%r, %opt, @optKey, @defVal, @list, $dieMess,
        $scrollN, $lineN, $warnval);

    # Get arguments.
    %r = %{ pop() } if ref($_[-1]) eq 'HASH';
    foreach (@_){
        if ( ref() eq 'ARRAY' ){
            push @list, @$_;
        } else {
            push @list, $_;
        }
    }
    $dieMess = "\nPrintMore() used incorrectly:";
    DieClean("$dieMess no print argument given.") unless @list;

    # Process the options.
    @optKey = qw(scroll begin end prefix number nonew final);
    @defVal = (20, 0, $#list, "", 0, 0, 0);
    foreach my $i (0 .. $#optKey){
        $opt{$optKey[$i]} = $defVal[$i];
        $opt{$optKey[$i]} = $r{$optKey[$i]} if defined $r{$optKey[$i]};
    }
    foreach my $k ( qw(scroll begin end) ){  # Must be positive integers
        DieClean("$dieMess $k option must be a positive integer.")
            if $opt{$k} =~ /\D/;
    }
    DieClean("$dieMess scroll value must be at least 1.") if $opt{scroll} < 1;
    return if $opt{end} < $opt{begin}; # Nothing to print!

    # Print the list.
    for my $i ($opt{begin} .. $opt{end}) {
        last if $i > $#list; # End of list reached.
        print $opt{prefix};
        if ( $opt{number} ){
            $lineN ++;
            printf "%4d. ", $lineN;
        }
        print $list[$i];
        print "\n" unless $opt{nonew};
        $scrollN ++;
        if ( $scrollN == $opt{scroll} and $i < $opt{end} ) {
            last if YesNo("-- ENTER for more, or 'q' to quit listing --", 'q');
            $scrollN = 0;
        }
    }
    if ($opt{final}){
        print "-- End of listing; ENTER to continue -- ";
        <STDIN>;
    }
}


__END__

